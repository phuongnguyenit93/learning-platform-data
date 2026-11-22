# Thiết kế các bước build với đầu vào, đầu ra và quan hệ phụ thuộc

Một build Gradle đáng tin cậy cần mô tả rõ ba điều: mỗi bước cần dữ liệu nào, tạo ra dữ liệu nào và phụ thuộc vào bước nào. Khi các quan hệ này được khai báo đầy đủ, Gradle có thể xây dựng task graph đúng, chạy các task theo thứ tự cần thiết, tránh thực thi công việc không cần thiết và tái sử dụng output an toàn.

Ngược lại, nếu build chỉ dựa vào thứ tự lệnh, đường dẫn file tự ghép hoặc trạng thái ngầm trên máy, nó có thể chạy đúng trong một lần thử nhưng thất bại khi chạy từ trạng thái sạch, chạy task trực tiếp, bật parallel execution hoặc chuyển sang CI.

Bài này hướng dẫn thiết kế một pipeline build theo mô hình **input → task → output**, cách nối các bước bằng Provider, phân biệt dependency dữ liệu với ràng buộc thứ tự, tổ chức lifecycle task và áp dụng mô hình đó cho một dự án nhiều bước.

## 1. Mô hình cơ bản: input, task và output

Một task là một đơn vị công việc trong Gradle. Nó nhận input, thực hiện một hành động và có thể tạo output.

~~~text
             Input
       source / config / tool
                 |
                 v
          +-------------+
          |    Task     |
          |  transform  |
          +-------------+
                 |
                 v
              Output
        file / directory / report
~~~

Ví dụ trong một dự án Java:

- Source file là input của task biên dịch.
- Compile classpath là input bổ sung của compiler.
- Class file là output của task biên dịch.
- Class file và runtime dependency là input của task đóng gói.
- JAR là output của task đóng gói.
- JAR và test configuration là input của các bước kiểm thử phù hợp.

Một build có nhiều task sẽ tạo thành một mạng lưới quan hệ:

~~~text
Java source -----------+
                       |
Compile classpath -----+----> compileJava ----> class files
                                                   |
                                                   v
Resources ------------------------------------> processResources
                                                   |
                                                   v
                                           classes output
                                                   |
                                                   v
                                              jar task
                                                   |
                                                   v
                                                app.jar
                                                   |
                                                   v
                                           integration test
~~~

Sơ đồ là mô hình khái niệm. Gradle plugin có thể tạo thêm task, output và dependency cụ thể. Điều quan trọng là mỗi task phải mô tả đúng dữ liệu nó cần và dữ liệu nó sở hữu.

### Ba câu hỏi khi thiết kế mỗi bước

Với từng task, hãy trả lời:

1. **Input:** Những file, giá trị, dependency, tool hoặc cấu hình nào ảnh hưởng đến kết quả?
2. **Output:** Task tạo hoặc cập nhật những file/thư mục nào?
3. **Dependency:** Task nào phải cung cấp dữ liệu hoặc hoàn thành trước task này?

Nếu không trả lời được một trong ba câu hỏi, task có nguy cơ phụ thuộc vào trạng thái ẩn hoặc tạo ra build graph không đầy đủ.

## 2. Task graph là cách Gradle tổ chức các bước build

Gradle không đơn giản chạy từng dòng trong build script theo thứ tự từ trên xuống. Build script chủ yếu cấu hình project và đăng ký task. Khi người dùng yêu cầu một task, Gradle xác định các task cần thiết và xây dựng graph phụ thuộc.

Ví dụ:

~~~groovy
tasks.register('compileModel') {
    doLast {
        println 'Compile model'
    }
}

tasks.register('packageModel') {
    dependsOn tasks.named('compileModel')

    doLast {
        println 'Package model'
    }
}
~~~

Khi chạy:

~~~shell
./gradlew packageModel
~~~

Gradle đưa compileModel vào graph vì packageModel khai báo dependsOn. Task compileModel phải chạy trước packageModel.

~~~text
packageModel requested
        |
        v
   packageModel
        |
        | dependsOn
        v
   compileModel
        |
        v
   execution order
   compileModel
        |
        v
   packageModel
~~~

Task graph chỉ chứa những task cần thiết cho các task được yêu cầu và dependency của chúng. Một task được khai báo trong build script không có nghĩa nó sẽ chạy ở mọi lần build.

### Đăng ký task không phải thực thi task

Ví dụ:

~~~groovy
tasks.register('generateIndex') {
    doLast {
        println 'Generate index'
    }
}
~~~

Đoạn này đăng ký task. Action chỉ chạy khi task được yêu cầu trực tiếp hoặc được thêm vào graph qua dependency.

Điều này cho phép Gradle cấu hình build theo cách lazy và chỉ thực thi công việc cần thiết.

## 3. Phân biệt dependency dữ liệu với dependency thứ tự

Một build thường có nhiều kiểu quan hệ task. Cần chọn đúng loại để Gradle hiểu cả graph lẫn dữ liệu.

| Cơ chế | Ý nghĩa | Có tự đưa task producer vào graph? | Truyền dữ liệu? |
|---|---|---:|---:|
| Task output Provider nối vào task input | Consumer cần output do producer tạo | Có thể suy ra tự động | Có |
| dependsOn | Consumer cần task khác được thực thi | Có | Không tự truyền dữ liệu |
| mustRunAfter | Nếu cả hai task được chọn, task này chạy sau task kia | Không | Không |
| shouldRunAfter | Gợi ý thứ tự nếu không tạo xung đột | Không | Không |
| finalizedBy | Chạy finalizer sau task được finalize | Có thể đưa finalizer vào graph | Không |
| builtBy trên file collection | File collection được tạo bởi task cụ thể | Có thể suy ra khi collection được dùng | Có file collection |

### dependsOn dùng khi cần một task khác

Ví dụ, task kiểm tra release cần task kiểm tra metadata hoàn thành trước:

~~~groovy
tasks.register('releaseGate') {
    dependsOn tasks.named('verifyMetadata')
}
~~~

Ở đây releaseGate không nhất thiết nhận file output trực tiếp từ verifyMetadata. Nó chỉ cần task đó được thực thi.

### mustRunAfter không thay thế dependsOn

~~~groovy
tasks.named('packageApp') {
    mustRunAfter tasks.named('generateConfig')
}
~~~

Quy tắc này chỉ có hiệu lực nếu cả packageApp và generateConfig đã được chọn vào graph. Nếu người dùng chạy packageApp riêng, mustRunAfter không tự thêm generateConfig.

Nếu packageApp cần file do generateConfig tạo, hãy nối output provider hoặc khai báo dependsOn cùng input thích hợp.

### shouldRunAfter là gợi ý thứ tự

shouldRunAfter hữu ích khi muốn ưu tiên một thứ tự nhưng không muốn tạo dependency cứng. Gradle có thể bỏ qua ordering rule nếu việc áp dụng nó gây vấn đề với graph hoặc parallel execution.

Không dùng shouldRunAfter để biểu diễn quan hệ dữ liệu bắt buộc.

### finalizedBy cho bước kết thúc

Một task có thể cần task khác chạy sau khi hoàn thành, ví dụ dọn tài nguyên tạm hoặc thu thập dữ liệu chẩn đoán:

~~~groovy
tasks.named('integrationTest') {
    finalizedBy tasks.named('collectTestEvidence')
}
~~~

Finalizer phù hợp với công việc cần chạy sau task ngay cả khi task được finalize thất bại trong những điều kiện Gradle hỗ trợ. Nó không phải cơ chế thay thế dependency giữa hai bước tạo và sử dụng output.

## 4. Khai báo input và output để Gradle hiểu task

Gradle cần metadata về task để biết task có thể được bỏ qua, cache hoặc chạy lại khi nào. Custom task nên dùng managed properties và annotation phù hợp.

Các annotation thường gặp:

| Annotation | Mục đích |
|---|---|
| @Input | Giá trị scalar ảnh hưởng output |
| @InputFile | Một file input |
| @InputFiles | Tập file input |
| @InputDirectory | Thư mục input |
| @Classpath | Classpath input |
| @CompileClasspath | Compile classpath với normalization phù hợp |
| @OutputFile | Một file output |
| @OutputDirectory | Một thư mục output |
| @Nested | Object chứa các property được khai báo |
| @Internal | Property không được fingerprint như input/output |
| @LocalState | Trạng thái local của task, không phải output có thể chia sẻ |

Ví dụ, một task nhận tên môi trường và file cấu hình rồi tạo report:

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

abstract class CreateEnvironmentReport extends DefaultTask {
    @Input
    abstract Property<String> getEnvironmentName()

    @InputFile
    @PathSensitive(PathSensitivity.NONE)
    abstract RegularFileProperty getConfigurationFile()

    @OutputFile
    abstract RegularFileProperty getReportFile()

    @TaskAction
    void createReport() {
        def config = configurationFile.get().asFile
        def report = reportFile.get().asFile

        report.parentFile.mkdirs()
        report.text = [
            "Environment: " + environmentName.get(),
            "Config file: " + config.name,
            "Config bytes: " + config.length()
        ].join(System.lineSeparator())
    }
}
~~~

Đăng ký task:

~~~groovy
tasks.register('createEnvironmentReport', CreateEnvironmentReport) {
    environmentName.set(
        providers.gradleProperty('environmentName').orElse('development')
    )

    configurationFile.set(
        layout.projectDirectory.file('config/app.properties')
    )

    reportFile.set(
        layout.buildDirectory.file('reports/environment.txt')
    )
}
~~~

Trong ví dụ:

- environmentName là input scalar.
- configurationFile là input file.
- reportFile là output file.
- Đường dẫn output nằm trong build directory do Gradle quản lý.

Nếu nội dung file cấu hình thay đổi, task có thể được chạy lại. Nếu property environmentName đổi, task cũng nhận biết input khác. Nếu report output vẫn hợp lệ và input không đổi, Gradle có thể đánh dấu task up-to-date.

### Mọi dữ liệu ảnh hưởng kết quả đều phải là input

Nếu task còn đọc một biến môi trường, file template, system property hoặc version tool mà không khai báo, Gradle không thể fingerprint đầy đủ task.

Ví dụ không nên:

~~~groovy
@TaskAction
void createReport() {
    def region = System.getenv('DEPLOY_REGION')
    // Output phụ thuộc region nhưng region không được khai báo.
}
~~~

Có thể mô hình hóa giá trị môi trường thành property input:

~~~groovy
@Input
abstract Property<String> getDeployRegion()
~~~

Khi cấu hình task, truyền giá trị theo cách phù hợp với môi trường. Điều này làm cho quan hệ giữa dữ liệu và output rõ ràng.

Không nên đánh dấu @Internal cho một property thực sự ảnh hưởng output chỉ để tránh Gradle báo thay đổi input. Làm vậy có thể khiến task up-to-date hoặc cache hit sai.

## 5. Output phải thuộc quyền sở hữu rõ ràng của task

Mỗi task nên có output được xác định rõ và không xung đột với task khác.

Một số nguyên tắc:

- Ghi output vào build directory hoặc vùng output được chỉ định.
- Không ghi đè source file do developer quản lý.
- Không để hai task cùng ghi một file.
- Không ghi vào build directory của project khác.
- Khai báo tất cả output file/directory mà task tạo.
- Không dùng output của task khác như thư mục tạm không có contract.

Ví dụ:

~~~groovy
tasks.register('generateManifest') {
    def manifestFile = layout.buildDirectory.file('generated/manifest.txt')

    outputs.file(manifestFile)

    doLast {
        def output = manifestFile.get().asFile
        output.parentFile.mkdirs()
        output.text = 'manifest-version=1'
    }
}
~~~

Cách khai báo này phù hợp với task đơn giản hoặc thử nghiệm. Với logic build được dùng lâu dài, nên tạo task type riêng có managed properties, annotation và action rõ ràng.

### Một task có thể có nhiều output

~~~groovy
@OutputDirectory
abstract DirectoryProperty getGeneratedDirectory()
~~~

Khi task tạo nhiều file liên quan, một output directory có thể biểu diễn vùng output đó. Tuy nhiên, task cần đảm bảo chỉ ghi những file thuộc quyền sở hữu của nó và xử lý file cũ phù hợp.

Nếu output được chia thành nhiều vùng có ý nghĩa khác nhau, có thể khai báo nhiều output property riêng để contract rõ ràng hơn.

## 6. Provider là cách nối dữ liệu giữa các task

Gradle Provider biểu diễn một giá trị có thể được tính khi cần. Khi Provider đến từ output property của TaskProvider, nó có thể mang thông tin về task producer.

Đây là cơ chế quan trọng để nối task mà không tự ghép file path.

Giả sử task A tạo file:

~~~groovy
abstract class GenerateCatalogTask extends DefaultTask {
    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void generate() {
        def output = outputFile.get().asFile
        output.parentFile.mkdirs()
        output.text = 'catalog-generated'
    }
}
~~~

Đăng ký task producer:

~~~groovy
def generateCatalog = tasks.register(
    'generateCatalog',
    GenerateCatalogTask
) {
    outputFile.set(
        layout.buildDirectory.file('generated/catalog.txt')
    )
}
~~~

Task B nhận output của task A:

~~~groovy
abstract class VerifyCatalogTask extends DefaultTask {
    @InputFile
    @PathSensitive(PathSensitivity.NONE)
    abstract RegularFileProperty getCatalogFile()

    @OutputFile
    abstract RegularFileProperty getReportFile()

    @TaskAction
    void verify() {
        def catalog = catalogFile.get().asFile
        def report = reportFile.get().asFile

        if (!catalog.exists() || catalog.length() == 0) {
            throw new GradleException('Catalog is missing or empty')
        }

        report.parentFile.mkdirs()
        report.text = 'Catalog verified: ' + catalog.name
    }
}
~~~

Nối output provider:

~~~groovy
tasks.register('verifyCatalog', VerifyCatalogTask) {
    catalogFile.set(
        generateCatalog.flatMap { it.outputFile }
    )

    reportFile.set(
        layout.buildDirectory.file('reports/catalog-verification.txt')
    )
}
~~~

Dòng nối dữ liệu là:

~~~groovy
catalogFile.set(generateCatalog.flatMap { it.outputFile })
~~~

Gradle biết input catalogFile đến từ outputFile của generateCatalog. Vì vậy, khi verifyCatalog được yêu cầu, producer có thể được đưa vào task graph và chạy trước consumer nếu output cần được tạo.

Consumer không phải tự đoán file nằm ở đâu.

### map và flatMap

TaskProvider có thể được biến đổi để lấy một property của task:

- map dùng khi callback trả về một giá trị/provider theo kiểu lồng phù hợp.
- flatMap dùng khi callback trả về một Provider và cần làm phẳng provider lồng nhau.

Trong trường hợp lấy RegularFileProperty từ TaskProvider, flatMap là cách phổ biến:

~~~groovy
generateCatalog.flatMap { it.outputFile }
~~~

Cách này giữ tính lazy và tránh realize task quá sớm trong configuration phase.

### Provider của path không nhất thiết biết producer

Ví dụ:

~~~groovy
def catalogPath = layout.buildDirectory.file('generated/catalog.txt')
~~~

Provider này biểu diễn vị trí file. Nó không tự nói rằng task generateCatalog tạo file đó.

Nếu consumer chỉ nhận catalogPath, Gradle có thể không biết cần chạy producer. Hãy lấy provider từ output property của task hoặc gắn producer bằng builtBy khi dùng file collection phù hợp.

## 7. Ví dụ tổng hợp: generate → verify → package

Một pipeline nhỏ có thể gồm ba bước:

1. generateCatalog tạo catalog file từ thư mục schema.
2. verifyCatalog đọc file được tạo và tạo report xác minh.
3. packageCatalog đóng gói catalog thành ZIP.

~~~text
Schema files
     |
     v
generateCatalog
     |
     +--------------------+
     |                    |
     v                    v
verifyCatalog        packageCatalog
     |                    |
     v                    v
verification report   catalog.zip
~~~

Mỗi consumer nhận output provider từ producer. Vì verifyCatalog và packageCatalog đều cần catalog, Gradle có thể đưa generateCatalog vào graph một lần và thực thi nó trước cả hai task.

### Định nghĩa producer

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.GradleException
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.api.tasks.Internal
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input

abstract class GenerateCatalogTask extends DefaultTask {
    @InputDirectory
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract DirectoryProperty getSchemaDirectory()

    @Input
    abstract Property<String> getCatalogFormat()

    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void generate() {
        def schemaRoot = schemaDirectory.get().asFile
        def output = outputFile.get().asFile

        def names = project.fileTree(schemaRoot) {
            include '**/*.yaml'
            include '**/*.yml'
        }.files.collect { file ->
            schemaRoot.toPath().relativize(file.toPath()).toString()
        }.sort()

        output.parentFile.mkdirs()
        output.text = (
            'format=' + catalogFormat.get() +
            System.lineSeparator() +
            names.join(System.lineSeparator())
        )
    }
}
~~~

Task nhận thư mục schema và format version. Output là một file catalog trong build directory.

### Định nghĩa consumer xác minh

~~~groovy
abstract class VerifyCatalogTask extends DefaultTask {
    @InputFile
    @PathSensitive(PathSensitivity.NONE)
    abstract RegularFileProperty getCatalogFile()

    @OutputFile
    abstract RegularFileProperty getReportFile()

    @TaskAction
    void verify() {
        def catalog = catalogFile.get().asFile
        def report = reportFile.get().asFile
        def lines = catalog.readLines('UTF-8')

        if (lines.size() < 2) {
            throw new GradleException('Catalog does not contain schema entries')
        }

        report.parentFile.mkdirs()
        report.text = 'Verified entries: ' + (lines.size() - 1)
    }
}
~~~

Task đọc file được tạo và sinh report. Nếu catalog thiếu dữ liệu cần thiết, task ném GradleException và build thất bại với thông báo cụ thể.

### Đăng ký task và nối provider

~~~groovy
plugins {
    id 'base'
}

def generateCatalog = tasks.register(
    'generateCatalog',
    GenerateCatalogTask
) {
    schemaDirectory.set(
        layout.projectDirectory.dir('src/main/schema')
    )
    catalogFormat.convention('v1')
    outputFile.set(
        layout.buildDirectory.file('generated/catalog/catalog.txt')
    )
}

def verifyCatalog = tasks.register(
    'verifyCatalog',
    VerifyCatalogTask
) {
    catalogFile.set(
        generateCatalog.flatMap { it.outputFile }
    )
    reportFile.set(
        layout.buildDirectory.file('reports/catalog/verification.txt')
    )
}

def packageCatalog = tasks.register('packageCatalog', Zip) {
    archiveBaseName.set('catalog')
    archiveVersion.set(project.version.toString())
    destinationDirectory.set(
        layout.buildDirectory.dir('distributions')
    )
    from(generateCatalog.flatMap { it.outputFile }) {
        rename { 'catalog.txt' }
    }
}

tasks.named('check') {
    dependsOn(verifyCatalog)
}

tasks.named('assemble') {
    dependsOn(packageCatalog)
}
~~~

Ví dụ này giả định các task type được đặt trong build logic mà build script có thể truy cập, và thư mục schema có ít nhất một file YAML. Trong một project thực tế, có thể đặt task type vào buildSrc hoặc convention plugin để tái sử dụng.

Task verifyCatalog và packageCatalog nhận provider của output producer. Gradle có thể suy ra dependency dữ liệu. Hai task được gắn vào lifecycle task check và assemble.

Với base plugin, check và assemble là các lifecycle task. Khi chạy build, Gradle có thể thực hiện cả hai nhánh:

~~~text
build
  |
  +--> check
  |      |
  |      v
  |   verifyCatalog
  |      |
  |      v
  |   generateCatalog
  |
  +--> assemble
         |
         v
     packageCatalog
         |
         v
     generateCatalog
~~~

Task generateCatalog chỉ xuất hiện một lần trong graph dù có nhiều consumer.

### Chạy từng mục tiêu

Chỉ tạo catalog:

~~~shell
./gradlew generateCatalog
~~~

Chỉ xác minh catalog:

~~~shell
./gradlew verifyCatalog
~~~

Chỉ đóng gói:

~~~shell
./gradlew packageCatalog
~~~

Chạy toàn bộ lifecycle:

~~~shell
./gradlew build
~~~

Khi chạy verifyCatalog hoặc packageCatalog trực tiếp, Gradle vẫn biết cần tạo catalog trước vì provider đã được nối đúng.

## 8. Khi nào cần dependsOn tường minh?

Provider wiring là lựa chọn tốt khi consumer nhận output của producer. Nhưng có những trường hợp consumer cần một task hoàn thành mà không trực tiếp tiêu thụ output.

Ví dụ:

- Task kiểm tra license cần chạy trước task release.
- Task xác minh môi trường phải hoàn tất trước một thao tác triển khai.
- Task tổng hợp kết quả cần chờ nhiều task kiểm tra.
- Lifecycle task gom nhóm các bước không có file output chung.

Khi đó có thể dùng:

~~~groovy
tasks.register('releaseCandidate') {
    dependsOn tasks.named('checkLicense')
    dependsOn tasks.named('verifyVersion')
    dependsOn tasks.named('assemble')
}
~~~

releaseCandidate là task tổng hợp, không nhất thiết thực hiện công việc nặng trong action. Nó đưa các task cần thiết vào graph.

### dependsOn không tự mô tả file nào được truyền

Nếu consumer cần file cụ thể, vẫn phải khai báo input:

~~~groovy
tasks.register('consumeCatalog') {
    dependsOn tasks.named('generateCatalog')

    doLast {
        def file = layout.buildDirectory.file(
            'generated/catalog/catalog.txt'
        ).get().asFile

        println file.text
    }
}
~~~

Đoạn này có dependency thực thi, nhưng consumer tự dựng path. Nếu producer đổi output path, consumer cần sửa. Tốt hơn là dùng task type có input property và truyền output provider.

## 9. Dùng FileCollection và builtBy khi cần tập file

Một task có thể tạo nhiều file hoặc một file collection được chia sẻ. Gradle hỗ trợ ConfigurableFileCollection và builtBy để mô tả nguồn tạo file.

Ví dụ:

~~~groovy
def generatedFiles = files(
    layout.buildDirectory.file('generated/report.json'),
    layout.buildDirectory.file('generated/summary.txt')
).builtBy(tasks.named('generateReports'))

tasks.register('archiveReports', Zip) {
    from(generatedFiles)
    archiveFileName.set('reports.zip')
    destinationDirectory.set(layout.buildDirectory.dir('distributions'))
}
~~~

builtBy khai báo task tạo các file trong collection. Khi archiveReports sử dụng collection, Gradle có thể đưa generateReports vào graph.

Nếu task producer có output property, nối trực tiếp property/provider thường rõ ràng hơn. builtBy hữu ích khi file collection được tạo từ nhiều nguồn hoặc cần gắn producer metadata vào một collection.

### builtBy không tạo file

builtBy chỉ mô tả quan hệ build. Task generateReports vẫn phải khai báo output và có action tạo đúng file. Nếu file không được tạo, archive task vẫn thất bại khi đọc input.

## 10. Tổ chức lifecycle task

Các plugin Gradle thường cung cấp task lifecycle để gom nhiều bước thành mục tiêu dễ gọi.

Với Java plugin, những task phổ biến gồm:

| Lifecycle/task | Vai trò |
|---|---|
| classes | Chuẩn bị output main classes và resources |
| testClasses | Chuẩn bị test classes |
| test | Chạy test |
| check | Chạy các bước verification |
| jar | Tạo JAR |
| assemble | Tạo các artifact của project |
| build | Gom verification và assemble |
| clean | Xóa output build của project |

Task lifecycle thường không chứa logic công việc chính. Nó tập hợp các task chuyên biệt qua dependency.

Ví dụ thêm bước xác minh vào check:

~~~groovy
tasks.named('check') {
    dependsOn tasks.named('verifyCatalog')
}
~~~

Thêm package tùy chỉnh vào assemble:

~~~groovy
tasks.named('assemble') {
    dependsOn tasks.named('packageCatalog')
}
~~~

Nhờ vậy, người dùng có thể gọi mục tiêu chuẩn:

~~~shell
./gradlew check
./gradlew assemble
./gradlew build
~~~

### Không tạo một task monolithic cho toàn bộ build

Một task duy nhất làm mọi việc như generate, validate, compile, package và publish thường khó bảo trì. Nó che giấu input/output, khó chạy riêng từng bước và khó tái sử dụng output.

Tách thành các task có trách nhiệm rõ ràng giúp:

- Chạy riêng bước cần điều tra.
- Gradle nhận biết input/output từng bước.
- Cache và up-to-date checking chính xác hơn.
- Parallel execution an toàn hơn khi task độc lập.
- Log cho biết bước nào thất bại.
- Dễ thay thế hoặc thêm bước trong pipeline.

## 11. Task độc lập có thể chạy song song

Nếu hai task không phụ thuộc dữ liệu của nhau và không ghi cùng output, Gradle có thể thực thi chúng song song khi parallel execution được bật và điều kiện phù hợp.

Ví dụ:

~~~text
          source files
           /       \
          v         v
    generateDocs  generateSchema
          |         |
          v         v
      docs.zip   schema.json
~~~

Hai task không có dependency giữa chúng. Chúng có thể chạy song song nếu không có resource conflict.

Sau đó task tổng hợp cần cả hai output:

~~~text
generateDocs ----+
                 |
                 v
             assembleBundle
                 ^
                 |
generateSchema --+
~~~

Consumer có thể nhận hai provider output:

~~~groovy
tasks.register('assembleBundle', Zip) {
    from(generateDocs.flatMap { it.outputDirectory })
    from(generateSchema.flatMap { it.outputFile })
    archiveFileName.set('bundle.zip')
}
~~~

Gradle có thể suy ra dependency từ các task output provider được đưa vào file collection của Zip task.

### Tránh shared mutable output

Nếu hai task cùng ghi một file, hoặc một task đọc file trong khi task khác đang sửa, parallel execution có thể tạo race condition.

Mỗi output nên có một producer rõ ràng. Nếu hai task cần cùng dữ liệu, hãy để chúng đọc output bất biến của producer sau khi producer hoàn thành.

## 12. Thiết kế task lazy và tránh cấu hình eager

Gradle khuyến khích task configuration avoidance để chỉ cấu hình task khi cần.

Ưu tiên:

~~~groovy
def compileModel = tasks.register('compileModel') {
    doLast {
        println 'Compile model'
    }
}

tasks.named('packageModel') {
    dependsOn(compileModel)
}
~~~

Hạn chế truy cập eager không cần thiết:

~~~groovy
tasks.create('compileModel') {
    doLast {
        println 'Compile model'
    }
}
~~~

tasks.register trả về TaskProvider. tasks.named tham chiếu task đã đăng ký mà không buộc task phải được realize ngay.

### Tránh afterEvaluate để nối dependency

Một cách cũ có thể gặp:

~~~groovy
afterEvaluate {
    tasks.named('packageModel') {
        dependsOn tasks.named('compileModel')
    }
}
~~~

Nếu có thể khai báo trực tiếp bằng provider và task registration, không cần trì hoãn cấu hình bằng afterEvaluate. afterEvaluate làm logic khó theo dõi, dễ phụ thuộc thứ tự evaluation và có thể gây khó khăn cho configuration cache hoặc project isolation.

### Tránh get() quá sớm

Ví dụ:

~~~groovy
def output = generateCatalog.get().outputFile.get().asFile
~~~

Lấy giá trị file trong configuration phase có thể buộc Gradle realize task hoặc tính property sớm hơn cần thiết. Hãy truyền provider đến nơi sử dụng:

~~~groovy
generateCatalog.flatMap { it.outputFile }
~~~

Chỉ gọi get() trong task action khi task thực sự cần file/value để thực thi.

## 13. Thiết kế task trong build nhiều project

Một Gradle build nhiều project có thể có task graph trải qua nhiều project.

Ví dụ:

~~~text
:contracts
    |
    v
:service
    |
    v
:application
~~~

Nếu application cần thư viện do service cung cấp, dùng project dependency:

~~~groovy
// application/build.gradle
dependencies {
    implementation project(':service')
}
~~~

Project dependency mô tả component cần dùng. Gradle chọn variant và task cần thiết để tạo component.

Nếu consumer cần artifact tùy chỉnh như schema hoặc report, producer có thể công bố outgoing configuration và consumer resolve project dependency đến configuration đó.

### Không truy cập task của project khác chỉ để lấy file

Một cách ghép chặt có thể trông như:

~~~groovy
def producer = project(':contracts').tasks.named('generateSchema')
~~~

Truy cập task của project khác để điều phối workflow thường làm build phụ thuộc cấu trúc nội bộ của producer. Với component Java, ưu tiên project dependency. Với artifact tùy chỉnh, ưu tiên outgoing configuration/variant. Với task trong cùng project, nối output provider trực tiếp.

### Project dependency khác task dependency

| Nhu cầu | Cơ chế nên xem xét |
|---|---|
| Application sử dụng thư viện service | Project dependency |
| Consumer nhận schema artifact từ contracts | Outgoing configuration và dependency |
| Task B nhận file do task A trong cùng project tạo | Output provider nối vào input |
| Một lifecycle task cần chạy nhiều verification task | dependsOn |
| Hai task cần có thứ tự nhưng không phụ thuộc dữ liệu | Ordering rule phù hợp |

## 14. Đầu vào và đầu ra của task quyết định up-to-date checking

Gradle có thể đánh dấu task UP-TO-DATE khi input không thay đổi và output hiện có còn hợp lệ.

Ví dụ:

~~~text
Lần đầu
schema + format version
        |
        v
 generateCatalog
        |
        v
 catalog.txt

Lần sau
same schema + same format
        |
        v
 output còn hợp lệ
        |
        v
 UP-TO-DATE
~~~

Nếu schema thay đổi, task cần thực thi lại. Nếu output bị xóa, task không thể chỉ dựa vào input không đổi để kết luận up-to-date.

### Output provider cũng tạo dependency dữ liệu

Khi consumer dùng output provider, Gradle hiểu producer cần chạy nếu output chưa có hoặc không còn hợp lệ.

Đó là lý do nối provider tốt hơn tự ghép path. Provider vừa mang giá trị file, vừa có thể mang task dependency metadata.

### Không khai báo output thì task có thể luôn chạy

Task không có output thường không thể được đánh dấu up-to-date theo cách thông thường. Điều này phù hợp với task có side effect hoặc chỉ kiểm tra một điều kiện không tạo report. Nhưng nếu task thực sự tạo file, cần khai báo output để Gradle quản lý.

## 15. Build cache yêu cầu task xác định từ input

Nếu task được thiết kế cacheable, Gradle có thể lưu output theo cache key. Cache key dựa trên implementation và các input được khai báo cùng normalization phù hợp.

Ví dụ custom task cacheable:

~~~groovy
import org.gradle.api.tasks.CacheableTask

@CacheableTask
abstract class NormalizeCatalogTask extends DefaultTask {
    @InputFile
    @PathSensitive(PathSensitivity.NONE)
    abstract RegularFileProperty getInputFile()

    @Input
    abstract Property<String> getLineEnding()

    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void normalize() {
        def source = inputFile.get().asFile.getText('UTF-8')
        def normalized = source.replace('\r\n', '\n')
        if (lineEnding.get() == 'CRLF') {
            normalized = normalized.replace('\n', '\r\n')
        }

        def output = outputFile.get().asFile
        output.parentFile.mkdirs()
        output.setText(normalized, 'UTF-8')
    }
}
~~~

Task có input file, input option và output file. Nếu cùng implementation và input, Gradle có thể khôi phục output từ build cache.

Chỉ đánh dấu @CacheableTask khi task có thể tái tạo output xác định từ các input đã khai báo. Không cache task publish, deploy hoặc gửi thông báo chỉ vì task đó có file output phụ.

### Input thiếu nguy hiểm hơn cache miss

Nếu input thay đổi mà không được khai báo, Gradle có thể tái sử dụng output sai. Hãy ưu tiên tính đúng đắn của input/output contract trước khi tối ưu cache hit.

## 16. Incremental execution là một lựa chọn riêng

Một task có thể xử lý riêng các file thay đổi thay vì chạy lại toàn bộ dữ liệu.

Ví dụ task phân tích hàng nghìn file schema có thể nhận InputChanges và chỉ xử lý file được thêm, sửa hoặc xóa. Khi đó task vẫn thực thi, nhưng chỉ làm phần công việc cần thiết.

~~~groovy
import org.gradle.work.InputChanges
import org.gradle.api.tasks.Incremental

@Incremental
@InputDirectory
@PathSensitive(PathSensitivity.RELATIVE)
abstract DirectoryProperty getSchemaDirectory()

@TaskAction
void process(InputChanges changes) {
    changes.getFileChanges(schemaDirectory).each { change ->
        switch (change.changeType) {
            case ADDED:
            case MODIFIED:
                // Process changed file.
                break
            case REMOVED:
                // Remove derived output for removed file.
                break
        }
    }
}
~~~

Task phải xử lý cả file bị xóa và lần chạy không có lịch sử incremental phù hợp. Nếu output được tạo theo từng input file, cần có quy tắc xóa output dẫn xuất tương ứng.

Incremental execution khác up-to-date checking và build cache:

- Up-to-date: task không cần chạy action.
- From cache: output được khôi phục.
- Incremental: task action chạy và xử lý change set.
- Full execution: task xử lý toàn bộ input.

## 17. Không biến thứ tự lệnh shell thành build model

Một pipeline bên ngoài có thể gọi:

~~~shell
./gradlew generateCatalog
./gradlew verifyCatalog
./gradlew packageCatalog
~~~

Thứ tự này chạy được trong một shell, nhưng nếu ai đó gọi trực tiếp:

~~~shell
./gradlew packageCatalog
~~~

thì producer có thể không chạy nếu quan hệ dependency chưa được khai báo.

Tốt hơn là mô hình hóa dependency trong Gradle. Khi đó một lệnh duy nhất có thể yêu cầu mục tiêu cuối:

~~~shell
./gradlew packageCatalog
~~~

Gradle tự thêm task producer cần thiết.

### Khi nào pipeline shell vẫn cần nhiều lệnh?

CI có thể cần nhiều lệnh khi có ranh giới giữa các Gradle build riêng biệt, runner khác nhau hoặc bước cần approval/credential riêng.

Ví dụ:

~~~text
Producer Gradle build
        |
        v
Publish to staging
        |
        v
CI artifact handoff
        |
        v
Independent consumer Gradle build
~~~

Đây là hai build độc lập. Task graph của producer không kéo task trong consumer build vào cùng graph. CI phải mô tả quan hệ giữa hai job và truyền artifact/repository cần thiết.

## 18. Cách quan sát task graph và dependency

Có một số lệnh hữu ích khi thiết kế hoặc chẩn đoán build.

Liệt kê task:

~~~shell
./gradlew tasks --all
~~~

Xem thông tin task:

~~~shell
./gradlew help --task packageCatalog
~~~

Xem graph dự kiến mà không thực thi task action:

~~~shell
./gradlew packageCatalog --dry-run
~~~

Chạy với log chi tiết:

~~~shell
./gradlew packageCatalog --info
~~~

Với build nhiều project, dùng task path đầy đủ:

~~~shell
./gradlew :application:jar
~~~

Task path giúp xác định task thuộc project nào và giảm phạm vi build cần điều tra.

### Đọc outcome của task

| Outcome | Ý nghĩa |
|---|---|
| SUCCESS | Task đã thực thi thành công |
| UP-TO-DATE | Output hiện có còn hợp lệ |
| FROM-CACHE | Output được khôi phục từ build cache |
| NO-SOURCE | Không có source phù hợp để xử lý |
| SKIPPED | Task bị bỏ qua theo điều kiện |
| FAILED | Task thất bại |

Một task không có dòng thực thi không nhất thiết bị lỗi. Hãy đọc outcome và lý do skip.

### --dry-run có giới hạn

--dry-run giúp quan sát task graph và thứ tự dự kiến. Nó không chạy task action, không chứng minh input tồn tại và không xác nhận chương trình con có thể thực thi thành công.

Dùng nó để kiểm tra quan hệ graph; sau đó chạy task thực tế để kiểm chứng dữ liệu và hành vi.

## 19. Những anti-pattern khi thiết kế các bước build

| Anti-pattern | Hậu quả | Hướng xử lý |
|---|---|---|
| Consumer tự ghép path output | Không biết producer nào tạo file | Nối output provider vào input |
| Chỉ dùng mustRunAfter cho dependency dữ liệu | Producer có thể không được chọn vào graph | Dùng provider hoặc dependsOn phù hợp |
| Task đọc file không khai báo input | Up-to-date/cache có thể sai | Khai báo input property |
| Task tạo file nhưng không khai báo output | Gradle khó quản lý output | Dùng @OutputFile/@OutputDirectory |
| Hai task cùng ghi một file | Race condition và output không xác định | Một producer cho mỗi output |
| Dùng afterEvaluate để nối task | Phụ thuộc thứ tự cấu hình, giảm khả năng lazy | Dùng TaskProvider và provider wiring |
| Gọi get() quá sớm | Realize task hoặc tính property sớm | Truyền provider, lấy giá trị trong action |
| Một task làm mọi việc | Khó chạy riêng, khó cache và khó điều tra | Chia task theo trách nhiệm |
| Chạy task producer thủ công trong CI | Consumer không tự mô tả dependency | Đưa dependency vào build model |
| Đọc task của project khác để lấy file | Coupling giữa project | Project dependency hoặc outgoing variant |
| Task có side effect nhưng đánh dấu cacheable | Cache hit không thực hiện side effect | Giữ task non-cacheable hoặc tách side effect |
| Ghi generated file vào source tree | Làm bẩn source và khó tái tạo | Ghi vào build/generated |

## 20. Quy trình thiết kế build từ yêu cầu đến task graph

Khi nhận yêu cầu build mới, hãy bắt đầu từ dữ liệu và kết quả mong muốn, sau đó mới chọn task.

### Bước 1 — Xác định deliverable

Ví dụ:

- JAR thư viện.
- ZIP distribution.
- Generated source.
- Schema catalog.
- Test report.
- Deployment bundle.

Mỗi deliverable cần có producer và vị trí output rõ ràng.

### Bước 2 — Xác định input

Liệt kê source, resource, config, toolchain, dependency, version và property ảnh hưởng đến output.

Không dựa vào file tồn tại sẵn trong workspace nếu file đó phải được tạo bởi task khác.

### Bước 3 — Chia công việc thành task

Mỗi task nên có một trách nhiệm dễ mô tả:

- Generate.
- Validate.
- Compile.
- Test.
- Package.
- Publish.

Không chia nhỏ chỉ để tăng số task; tách khi có ranh giới dữ liệu hoặc trách nhiệm có ý nghĩa.

### Bước 4 — Khai báo input/output

Dùng managed properties và annotation. Đảm bảo mọi dữ liệu ảnh hưởng kết quả đều được khai báo.

### Bước 5 — Nối dependency

- Task cùng project: truyền provider output vào input.
- Task cần hoàn thành trước nhưng không truyền dữ liệu: dependsOn.
- Project dùng component Java khác: project dependency.
- Artifact tùy chỉnh giữa project: outgoing configuration/variant.
- Hai build riêng: CI handoff hoặc repository.

### Bước 6 — Tổ chức lifecycle

Gắn verification vào check, package vào assemble hoặc lifecycle task phù hợp. Giữ task chuyên biệt có thể chạy độc lập.

### Bước 7 — Kiểm tra graph

Dùng --dry-run và task path để xác nhận producer được đưa vào khi gọi consumer trực tiếp.

### Bước 8 — Chạy từ trạng thái sạch

Xóa output theo quy trình clean rồi gọi mục tiêu cuối. Build phải tự tạo lại mọi output cần thiết.

### Bước 9 — Kiểm tra thay đổi input

Sửa một input và xác nhận task liên quan chạy lại. Các task không phụ thuộc dữ liệu thay đổi nên có thể tiếp tục up-to-date.

### Bước 10 — Kiểm tra cache và CI

Khi task model đã đúng, xem xét build cache, parallel execution và CI handoff. Không dùng cache để che giấu dependency graph thiếu.

## 21. Ví dụ thiết kế một pipeline ứng dụng Java

Giả sử một ứng dụng có các bước:

1. Kiểm tra schema.
2. Sinh Java source từ schema.
3. Biên dịch source.
4. Chạy unit test.
5. Đóng gói JAR.
6. Kiểm tra archive.
7. Tạo distribution.

Có thể biểu diễn:

~~~text
Schema files
     |
     v
validateSchema
     |
     v
generateSources
     |
     v
compileJava <----- Java source files
     |
     v
classes <--------- resources
     |
     +-------------------+
     |                   |
     v                   v
    test                jar
     |                   |
     v                   v
 test reports        application.jar
                         |
                         v
                    verifyArchive
                         |
                         v
                    distZip
~~~

Một số task là task do Java plugin tạo. Task custom chỉ cần bổ sung các bước mà plugin không cung cấp.

Ví dụ nối generated source vào source set:

~~~groovy
def generateSources = tasks.register(
    'generateSources',
    GenerateSourcesTask
) {
    schemaDirectory.set(
        layout.projectDirectory.dir('src/main/schema')
    )
    outputDirectory.set(
        layout.buildDirectory.dir('generated/sources/main')
    )
}

sourceSets {
    main {
        java.srcDir(
            generateSources.flatMap { it.outputDirectory }
        )
    }
}
~~~

Provider output directory cho Gradle biết source directory được tạo bởi task generator. Compile task có thể được nối với producer.

Nếu generator cần một task validation chạy trước, có thể nối input/output của validation hoặc khai báo dependsOn phù hợp. Không chỉ đặt mustRunAfter nếu validation là điều kiện bắt buộc.

### Gắn bước kiểm tra vào lifecycle

~~~groovy
tasks.named('check') {
    dependsOn tasks.named('validateSchema')
    dependsOn tasks.named('verifyArchive')
}
~~~

Trong thực tế, verifyArchive có thể phụ thuộc JAR output provider để Gradle biết archive phải được tạo trước khi kiểm tra.

### Tạo distribution từ artifact

~~~groovy
tasks.register('distZip', Zip) {
    archiveBaseName.set('orders-service')
    from(tasks.named('jar'))
    from('config') {
        into 'config'
    }
    destinationDirectory.set(
        layout.buildDirectory.dir('distributions')
    )
}
~~~

Đối với task Zip, dùng output của task jar làm input giúp Gradle nối dependency phù hợp. Có thể cấu hình thêm manifest, scripts và runtime dependencies theo nhu cầu của distribution.

## 22. Quan hệ giữa build logic và CI pipeline

Gradle task graph mô tả công việc bên trong một Gradle build. CI pipeline mô tả quan hệ rộng hơn giữa checkout, job, runner, approval và artifact handoff.

~~~text
CI workflow
    |
    v
Build job
    |
    +--> Gradle task graph
    |       generate
    |          |
    |       compile
    |          |
    |        test
    |          |
    |       package
    |
    v
Upload artifact
    |
    v
Independent verification job
    |
    v
Release/deploy job
~~~

Không nên dùng CI job order để bù cho một task dependency bị thiếu bên trong cùng build. Ngược lại, Gradle task dependency không tự chuyển file sang runner khác. Mỗi lớp cần mô tả quan hệ trong phạm vi của nó.

### Khi nào chia thành nhiều CI job?

Có thể tách job khi:

- Job chạy trên runner hoặc image khác.
- Có approval hoặc quyền truy cập riêng.
- Cần matrix theo OS/JDK/architecture.
- Consumer là một build độc lập.
- Artifact cần được upload/download.
- Cần tách trách nhiệm build, verification và deployment.

Nếu chỉ là các task trong cùng Gradle build và không có ranh giới môi trường/permission, thường có thể giữ chúng trong cùng task graph.

## 23. Determinism và khả năng tái tạo

Một task được mô hình hóa tốt nên tạo output xác định từ input đã khai báo.

Nếu cùng input nhưng output thay đổi do timestamp, random value, filesystem order hoặc environment không được khai báo, task khó up-to-date và khó cache đúng.

Các yếu tố cần kiểm soát:

- Sắp xếp danh sách file nếu thứ tự ảnh hưởng output.
- Khai báo encoding.
- Khai báo toolchain và version tool.
- Không đọc current working directory ngầm.
- Không nhúng absolute workspace path nếu không cần.
- Không dùng timestamp hiện tại trừ khi đó là input có chủ đích.
- Không phụ thuộc network response không được mô hình hóa.
- Dùng output directory riêng của task.

### Không dùng output cũ như input ẩn

Nếu task đọc một file trong build directory do lần build trước tạo nhưng không khai báo producer, kết quả có thể phụ thuộc vào lịch sử workspace.

Hãy đảm bảo file đó được tạo bởi task có output property và consumer nhận provider. Khi chạy clean build, graph vẫn phải tạo đủ dữ liệu.

## 24. Kiểm tra task graph qua các tình huống

Một build tốt nên được kiểm tra với các cách gọi khác nhau.

| Tình huống | Điều cần xác nhận |
|---|---|
| Gọi task cuối trực tiếp | Producer được đưa vào graph |
| Chạy build từ trạng thái sạch | Output được tạo đúng thứ tự |
| Chạy lần thứ hai không đổi input | Task có thể up-to-date hoặc from-cache |
| Thay một input | Task liên quan chạy lại |
| Xóa một output | Producer được chạy lại hoặc output được khôi phục từ cache |
| Bật parallel execution | Không có race condition trên output |
| Chạy task ở project consumer | Dependency project/artifact được resolve |
| Chạy trong CI runner sạch | Không phụ thuộc file local từ máy developer |

Lệnh kiểm tra graph:

~~~shell
./gradlew packageCatalog --dry-run
~~~

Lệnh chạy thực tế:

~~~shell
./gradlew clean packageCatalog --info
~~~

Lần chạy tiếp theo:

~~~shell
./gradlew packageCatalog --info
~~~

Nếu task model và output hợp lệ, lần chạy sau có thể cho thấy các task up-to-date. Kết quả cụ thể phụ thuộc task input/output và cache configuration.

## 25. Những nhầm lẫn thường gặp

| Dễ nhầm | Cách hiểu đúng |
|---|---|
| Viết task trước trong build script nghĩa nó chạy trước | Execution order được quyết định bởi task graph |
| dependsOn tự truyền output | Nó thêm task vào graph; consumer vẫn cần input/provider để nhận dữ liệu |
| mustRunAfter bảo đảm producer chạy | Nó chỉ sắp xếp thứ tự khi cả hai task được chọn |
| Provider path tự biết task tạo file | Chỉ provider gắn với task output hoặc file collection builtBy mới mô tả producer |
| Task nào cũng cần dependsOn tường minh | Provider output wiring có thể suy ra dependency |
| Task không có output vẫn up-to-date bình thường | Task không output thường cần thực thi lại, trừ cơ chế skip khác |
| Task output có thể được chia sẻ tùy ý | Mỗi output cần producer và ownership rõ |
| CI chạy producer trước là đủ | Người gọi task consumer trực tiếp vẫn cần dependency trong Gradle |
| Project dependency và task dependency giống nhau | Một cái nối component giữa project; một cái nối công việc trong graph |
| afterEvaluate luôn cần cho task liên project | Provider và plugin model thường cho phép wiring lazy |
| --dry-run chứng minh build chạy thành công | Nó chỉ quan sát graph, không chạy action |
| Cache hit chứng minh input được khai báo đầy đủ | Input thiếu có thể tạo cache hit sai |
| Một task lớn đơn giản hơn nhiều task nhỏ | Task tách theo trách nhiệm giúp graph, cache và chẩn đoán rõ hơn |

## 26. Bảng chọn cơ chế theo nhu cầu

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Task B cần file do task A tạo | Output Provider nối vào input |
| Task B cần task A hoàn thành nhưng không nhận file | dependsOn |
| Task A và B cần thứ tự nếu cùng được chọn | mustRunAfter hoặc shouldRunAfter |
| Chạy cleanup/report sau task | finalizedBy |
| File collection được tạo bởi task cụ thể | builtBy |
| Project Java dùng thư viện project khác | project dependency |
| Project khác dùng artifact tùy chỉnh | Consumable configuration/variant |
| Nhiều task được gom thành mục tiêu chuẩn | Lifecycle task và dependsOn |
| Job CI cần file từ runner khác | CI artifact upload/download |
| Task cần bỏ qua khi input không đổi | Khai báo input/output chính xác |
| Task cần xử lý một phần file thay đổi | InputChanges và @Incremental |
| Task output có thể tái sử dụng giữa build | @CacheableTask và build cache |

## 27. Checklist thiết kế cho mỗi task

Trước khi đưa task vào build, hãy xác nhận:

- [ ] Tên task thể hiện hành động cụ thể.
- [ ] Task có một trách nhiệm rõ ràng.
- [ ] Mọi input ảnh hưởng output đều được khai báo.
- [ ] Output file/directory được khai báo và thuộc quyền sở hữu của task.
- [ ] Output được đặt ở vị trí phù hợp trong build directory.
- [ ] Consumer nhận output bằng provider hoặc file collection có producer metadata.
- [ ] Dependency thứ tự được biểu diễn bằng cơ chế phù hợp.
- [ ] Task không phụ thuộc file cũ hoặc trạng thái ẩn trên máy.
- [ ] Task có thể chạy trực tiếp mà vẫn có đủ dependency.
- [ ] Không có hai task cùng ghi một output.
- [ ] Cacheability chỉ được bật khi output xác định từ input.
- [ ] Task action không làm công việc cấu hình hoặc resolve dữ liệu không cần thiết.
- [ ] Có thể quan sát task graph bằng task path và --dry-run.

Checklist này là công cụ thiết kế, không phải lý do để thêm annotation hoặc dependency một cách máy móc. Mỗi property và quan hệ cần phản ánh hành vi thực tế của task.

## 28. Nguyên tắc thiết kế build có thể bảo trì

Một build dễ hiểu bắt đầu từ contract rõ ràng cho từng bước. Producer công bố output; consumer khai báo input; Gradle nối hai phía và xây dựng graph. Task dependency được dùng khi cần thực thi một công việc khác, còn ordering rule chỉ được dùng cho thứ tự.

Khi các quan hệ đó được mô hình hóa đúng, người dùng có thể gọi task cuối trực tiếp, chạy từ trạng thái sạch, bật parallel execution và chuyển build sang CI mà không cần nhớ một chuỗi lệnh thủ công. Gradle cũng có đủ thông tin để thực hiện up-to-date checking, build cache và configuration avoidance một cách chính xác.

Hãy thiết kế mỗi task quanh dữ liệu nó nhận và tạo ra. Một task graph đúng không chỉ giúp build chạy theo đúng thứ tự; nó còn làm cho output có thể truy vết, tái sử dụng và kiểm chứng qua toàn bộ quy trình build.

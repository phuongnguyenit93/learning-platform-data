# Đầu ra giữa các mô-đun và tránh phụ thuộc vào đường dẫn thủ công

Trong một Gradle build nhiều mô-đun, một mô-đun thường tạo ra dữ liệu mà mô-đun khác cần sử dụng. Ví dụ, project **:domain** biên dịch thành thư viện để **:app** sử dụng; project **:schema** sinh mã Java để **:service** biên dịch; hoặc một task tạo file metadata để task khác kiểm tra.

Cách nối các mô-đun rất quan trọng. Nếu mô-đun tiêu thụ tự ghép đường dẫn như **../domain/build/libs/domain.jar**, build sẽ phụ thuộc vào cấu trúc thư mục, tên file và thời điểm task tạo output. Cách này dễ hỏng khi đổi thư mục build, đổi tên artifact, chạy build song song, dùng cache hoặc chuyển project sang một thư mục khác.

Gradle có các cơ chế để mô tả quan hệ giữa **producer** (mô-đun tạo output) và **consumer** (mô-đun sử dụng output): project dependency, configuration/variant, task output, provider và file collection. Khi khai báo đúng quan hệ, Gradle có thể xác định output đến từ đâu, task nào phải chạy trước và file nào cần được truyền cho consumer.

## 1. Producer và consumer trong build nhiều mô-đun

Một mô-đun là **producer** khi nó sở hữu công việc tạo ra artifact hoặc file. Một mô-đun là **consumer** khi nó khai báo nhu cầu sử dụng artifact hoặc file đó.

Ví dụ:

~~~text
Gradle build
  |
  +--> :domain
  |      +--> compileJava
  |      +--> jar
  |              |
  |              +--> domain library artifact
  |
  +--> :app
         +--> compileJava
         +--> runtime
                 |
                 +--> uses :domain
~~~

Trong ví dụ này, **:domain** sở hữu mã nguồn và output của thư viện domain. **:app** cần thư viện đó để biên dịch và chạy. Quan hệ giữa hai project nên được khai báo bằng project dependency:

~~~groovy
// app/build.gradle
dependencies {
    implementation project(':domain')
}
~~~

Gradle biết **:app** cần component do **:domain** cung cấp. Nó có thể lựa chọn variant phù hợp cho compile hoặc runtime, đồng thời nối các công việc cần thiết vào build graph.

Consumer không cần biết JAR nằm trong thư mục domain/build/libs, tên archive là gì hoặc project có thay đổi thư mục output hay không. Những chi tiết đó thuộc về producer và Gradle.

### Hai loại quan hệ thường bị nhầm

Cần phân biệt:

- **Dependency giữa project/module**: mô tả consumer cần component nào từ producer.
- **Dependency giữa task**: mô tả task nào cần chạy trước task nào hoặc cần output của task nào.

Project dependency thường tạo ra quan hệ build cần thiết giữa các project. Task output provider tạo ra quan hệ dữ liệu giữa các task. Chỉ khai báo thứ tự task không nhất thiết truyền dữ liệu; chỉ truyền một chuỗi đường dẫn cũng không nhất thiết làm Gradle biết task nào tạo ra file đó.

## 2. Vì sao đường dẫn thủ công dễ gây lỗi?

Một cách làm dễ gặp là đọc file output của project khác bằng đường dẫn tương đối:

~~~groovy
// app/build.gradle
dependencies {
    implementation files('../domain/build/libs/domain.jar')
}
~~~

Hoặc trong task:

~~~groovy
tasks.register('inspectDomain') {
    doLast {
        def file = file('../domain/build/libs/domain.jar')
        println file.absolutePath
    }
}
~~~

Các đoạn trên gắn consumer với một vị trí cụ thể trên filesystem. Chúng không mô tả đầy đủ quan hệ producer-consumer.

### Những vấn đề có thể xuất hiện

| Vấn đề | Vì sao xảy ra |
|---|---|
| Đổi tên project hoặc thư mục | Đường dẫn tương đối không còn trỏ đến vị trí cũ |
| Đổi tên archive hoặc version | Consumer đang giả định tên file cố định |
| Đổi thư mục build output | Đường dẫn không theo cấu hình output thực tế |
| Chạy task trực tiếp ở consumer | Gradle không biết cần chạy task producer để tạo file |
| Build song song | Consumer có thể đọc file trước khi producer tạo xong nếu thiếu task dependency |
| Clean build | File output chưa tồn tại khi consumer bắt đầu |
| Build cache | Gradle không có quan hệ producer rõ ràng để quản lý output đúng cách |
| Chuyển sang CI hoặc checkout path khác | Đường dẫn phụ thuộc cấu trúc máy hoặc thư mục làm việc |
| Thay artifact implementation | Consumer phải sửa theo tên file hoặc layout nội bộ của producer |

Một đường dẫn tương đối có thể chạy được trên máy lập trình viên vì output đã tồn tại từ lần build trước. Điều đó không chứng minh build graph đã được khai báo đúng. Khi chạy từ trạng thái sạch hoặc chỉ gọi task consumer, lỗi mới xuất hiện.

### Đường dẫn không phải contract giữa các mô-đun

Contract nên mô tả **thành phần nào được cung cấp và cách consumer sử dụng nó**. File path là chi tiết triển khai của producer hoặc của Gradle.

Ví dụ, **:domain** có thể chuyển từ JAR sang variant khác, thay đổi thư mục output hoặc được cung cấp từ một included build. Nếu consumer phụ thuộc vào project component, Gradle có thể xử lý thay đổi đó qua metadata/variant. Nếu consumer phụ thuộc vào chuỗi đường dẫn cố định, mọi thay đổi layout có thể buộc phải sửa consumer.

## 3. Thiết lập build nhiều project bằng settings.gradle

Trước khi khai báo project dependency, các project cần được đưa vào build từ settings file.

Ví dụ cấu trúc:

~~~text
shop/
  settings.gradle
  build.gradle
  domain/
    build.gradle
    src/main/java/...
  app/
    build.gradle
    src/main/java/...
~~~

File settings.gradle:

~~~groovy
rootProject.name = 'shop'
include 'domain', 'app'
~~~

Sau đó, trong app/build.gradle:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation project(':domain')
}
~~~

Project path **:domain** là định danh trong Gradle build. Nó không phải đường dẫn file tương đối được consumer tự ghép.

Nếu thư mục vật lý khác với tên project, có thể ánh xạ trong settings:

~~~groovy
include 'domain'
project(':domain').projectDir = file('modules/business-domain')
~~~

Consumer vẫn khai báo:

~~~groovy
dependencies {
    implementation project(':domain')
}
~~~

Việc thay đổi vị trí vật lý được quản lý tại settings. Các consumer vẫn dùng project path ổn định.

### Project path và filesystem path có vai trò khác nhau

| Định danh | Vai trò |
|---|---|
| **:domain** | Định danh project trong Gradle build |
| **modules/business-domain** | Vị trí thư mục được settings ánh xạ |
| **project(':domain')** | Tham chiếu component của project |
| **../domain/build/libs/domain.jar** | Đường dẫn file do consumer tự giả định |

Khi cấu trúc repository thay đổi, chỉ phần ánh xạ project cần được điều chỉnh nếu project path vẫn giữ nguyên. Các consumer không cần tự tính lại đường dẫn.

## 4. Dùng project dependency cho module Java

Với các mô-đun Java trong cùng Gradle build, project dependency thường là cách phù hợp để một mô-đun sử dụng thư viện do mô-đun khác tạo ra.

Ví dụ:

~~~groovy
// domain/build.gradle
plugins {
    id 'java-library'
}

dependencies {
    api 'org.example:money-api:1.0'
    implementation 'org.example:domain-internal:1.0'
}
~~~

~~~groovy
// app/build.gradle
plugins {
    id 'java'
}

dependencies {
    implementation project(':domain')
}
~~~

Khi **:app** cần biên dịch hoặc chạy, Gradle sử dụng component/variant được **:domain** cung cấp. Java Library plugin phân biệt API variant và runtime variant, vì vậy consumer có thể nhận dependency phù hợp với mục đích sử dụng.

Không nên thay project dependency bằng cách thêm file JAR được tạo trong thư mục build/libs. Project dependency cung cấp cho Gradle thông tin về project producer, variant, artifact và các quan hệ build cần thiết.

### Project dependency không có nghĩa consumer phải biết tên JAR

Tên archive của producer có thể thay đổi qua cấu hình:

~~~groovy
tasks.named('jar', Jar) {
    archiveBaseName = 'business-domain'
    archiveVersion = '2.0'
}
~~~

Consumer vẫn có thể dùng:

~~~groovy
dependencies {
    implementation project(':domain')
}
~~~

Gradle sử dụng metadata của project dependency để tìm artifact phù hợp. Consumer không cần sửa đường dẫn theo tên archive mới.

### Chọn api hay implementation ở consumer

Trong ứng dụng cuối cùng, dependency trực tiếp thường được khai báo bằng **implementation**. Nếu project consumer là thư viện và kiểu từ producer xuất hiện trong API công khai của consumer, cần xem xét **api** theo quy ước của Java Library plugin.

Ví dụ:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api project(':domain-api')
    implementation project(':domain-implementation')
}
~~~

**api** công khai dependency cho consumer tiếp theo trên compile API. **implementation** giữ dependency ở phía implementation của thư viện. Đây là quyết định về dependency visibility, không phải cách chọn file path.

## 5. Gradle variant và outgoing artifact

Project có thể cung cấp nhiều variant. Một variant mô tả thành phần dành cho một mục đích sử dụng cụ thể, kèm attributes và artifacts.

Với Java Library plugin, các configuration tiêu biểu gồm:

| Configuration | Vai trò |
|---|---|
| **apiElements** | Variant được consumer dùng cho compile API |
| **runtimeElements** | Variant được consumer dùng cho runtime |
| **implementation** | Nơi khai báo dependency nội bộ của producer |
| **api** | Nơi khai báo dependency công khai của producer |

Các configuration như **apiElements** và **runtimeElements** là những outgoing variants có thể được project khác tiêu thụ. Chúng có attributes giúp Gradle chọn variant phù hợp.

Consumer thường không cần gọi trực tiếp apiElements hoặc runtimeElements. Khai báo project dependency thông thường cho phép Gradle tự chọn variant theo compile/runtime usage và các attributes khác.

### Producer công bố component, consumer khai báo nhu cầu

~~~text
:domain
  |
  +--> apiElements
  |       +--> API artifact
  |       +--> API dependencies
  |
  +--> runtimeElements
          +--> Runtime artifact
          +--> Runtime dependencies
                 |
                 v
              :app
        requests compile/runtime usage
~~~

Cách tổ chức này tách contract của producer khỏi layout file. Consumer mô tả nhu cầu; Gradle chọn variant và artifact tương thích.

### Attributes ảnh hưởng lựa chọn variant

Variant có thể được mô tả bằng attributes như:

- Usage: compile hay runtime.
- Category: library, platform hoặc documentation.
- Library elements: dạng thành phần như JAR.
- Target JVM version: phiên bản JVM mục tiêu.
- Attributes do plugin hoặc build tự định nghĩa.

Nếu producer không có variant tương thích với yêu cầu consumer, Gradle có thể báo lỗi không tìm thấy variant phù hợp. Khi đó cần xem attributes và metadata, không nên sửa bằng cách hard-code một JAR path.

## 6. Nối output của task bằng Provider

Không phải mọi output đều là thư viện Java. Một task có thể sinh file schema, metadata, report, archive hoặc thư mục mã nguồn. Khi task khác cần output đó, hãy truyền provider của output thay vì tự ghép đường dẫn.

Gradle có các property như:

- **RegularFileProperty**: đại diện cho một file.
- **DirectoryProperty**: đại diện cho một thư mục.
- **Property<T>**: đại diện cho một giá trị được Gradle quản lý.
- **ConfigurableFileCollection**: đại diện cho tập file.
- **Provider<T>**: đại diện cho một giá trị có thể được tính khi cần.

Provider từ task output có thể mang theo thông tin về task tạo ra output. Khi provider được nối vào input của task khác, Gradle có thể suy ra quan hệ dependency giữa producer và consumer.

### Ví dụ task producer tạo file

Giả sử task GenerateCatalog tạo file JSON:

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction

abstract class GenerateCatalog extends DefaultTask {
    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void generate() {
        def output = outputFile.get().asFile
        output.parentFile.mkdirs()
        output.text = '{"catalog":"generated"}'
    }
}

def generateCatalog = tasks.register('generateCatalog', GenerateCatalog) {
    outputFile.set(layout.buildDirectory.file('generated/catalog.json'))
}
~~~

Task khai báo output thông qua RegularFileProperty và @OutputFile. Đường dẫn được producer tạo từ layout.buildDirectory, nên nó đi theo build directory đã cấu hình của project.

### Ví dụ task consumer nhận output provider

Consumer task có input file:

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.TaskAction

abstract class InspectCatalog extends DefaultTask {
    @InputFile
    abstract RegularFileProperty getCatalogFile()

    @TaskAction
    void inspect() {
        def input = catalogFile.get().asFile
        println "Reading: " + input.name
        println input.text
    }
}

tasks.register('inspectCatalog', InspectCatalog) {
    catalogFile.set(generateCatalog.flatMap { it.outputFile })
}
~~~

Dòng quan trọng là:

~~~groovy
catalogFile.set(generateCatalog.flatMap { it.outputFile })
~~~

Consumer lấy output property từ task provider. Gradle có thể nhận biết file này được tạo bởi generateCatalog, từ đó đưa producer task vào graph khi cần chạy consumer.

Chạy:

~~~shell
./gradlew inspectCatalog
~~~

Gradle sẽ thực hiện producer trước consumer khi output cần được tạo. Người viết consumer không cần biết đường dẫn vật lý generated/catalog.json.

### Vì sao dùng flatMap?

generateCatalog là TaskProvider của GenerateCatalog. Output outputFile là property của task. flatMap lấy provider của property bên trong task provider mà không buộc task phải được realize ngay trong lúc cấu hình.

Cách này giữ tính lazy của Gradle và giúp nối dữ liệu giữa task rõ ràng.

### Provider cần gắn với output do task sở hữu

Nếu chỉ tạo một provider từ chuỗi path:

~~~groovy
def catalogFile = layout.buildDirectory.file('generated/catalog.json')
~~~

provider này biểu diễn vị trí file nhưng tự nó không nói rõ task nào tạo ra file. Nếu consumer chỉ dùng provider path đó, Gradle có thể không biết cần chạy producer.

Hãy truyền provider từ task output hoặc khai báo builtBy/dependency tương ứng khi sử dụng file collection. Quan hệ producer phải được mô tả rõ, không thể suy ra chỉ từ việc hai task tình cờ dùng cùng một đường dẫn.

## 7. Dùng task dependency và output provider đúng mục đích

Có thể khai báo dependency tường minh:

~~~groovy
tasks.register('inspectCatalog') {
    dependsOn tasks.named('generateCatalog')

    doLast {
        def file = layout.buildDirectory.file('generated/catalog.json').get().asFile
        println file.text
    }
}
~~~

Đoạn này giúp Gradle biết producer phải chạy trước consumer. Tuy nhiên, consumer vẫn tự ghép đường dẫn output. Nếu producer đổi vị trí output, consumer phải được cập nhật theo.

Tốt hơn là truyền output provider vào task input như ví dụ trước. Cách đó thể hiện cả hai thông tin:

1. Consumer cần file nào.
2. Task nào tạo ra file đó.

| Cách nối | Task dependency | Dữ liệu output |
|---|---|---|
| Chỉ hard-code path | Không tự biết | Consumer tự tìm file |
| dependsOn(producer) + hard-code path | Có | Consumer vẫn tự tìm file |
| Truyền task output provider vào task input | Có thể suy ra từ provider | Dữ liệu được nối trực tiếp |
| File collection có builtBy(producer) | Có metadata producer | Consumer nhận file collection |

### Khi nào dependsOn vẫn phù hợp?

dependsOn phù hợp khi consumer cần producer hoàn thành nhưng không trực tiếp nhận một output property, ví dụ task điều phối một bước kiểm tra hoặc task lifecycle.

Nếu consumer cần file cụ thể, ưu tiên nối file vào input property. dependsOn chỉ mô tả thứ tự/dependency; nó không thay thế việc khai báo input.

### Không dùng mustRunAfter thay cho dependency dữ liệu

mustRunAfter chỉ ràng buộc thứ tự khi cả hai task đã được chọn vào graph. Nó không tự thêm producer vào graph và không truyền output cho consumer.

Nếu consumer cần file do producer tạo, dùng task output provider hoặc dependency phù hợp. Một quan hệ thứ tự đơn thuần không bảo đảm file tồn tại.

## 8. Chia sẻ output giữa các project

Khi output được tạo trong một project và tiêu thụ từ project khác, cần chọn cơ chế theo loại output.

### Trường hợp A: output là thư viện Java

Dùng project dependency:

~~~groovy
// app/build.gradle
dependencies {
    implementation project(':domain')
}
~~~

Đây là cách thông thường cho source code của một project sử dụng class của project Java khác. Gradle xử lý compile/runtime variant và task dependency phù hợp.

### Trường hợp B: output là artifact tùy chỉnh

Ví dụ project schema tạo file schema đã chuẩn hóa và project service cần đọc file đó. Có thể công bố file thông qua outgoing configuration của producer và resolve từ consumer.

Producer schema/build.gradle:

~~~groovy
import org.gradle.api.attributes.Usage

def generateSchema = tasks.register('generateSchema', GenerateSchemaTask) {
    outputFile.set(layout.buildDirectory.file('generated/schema.json'))
}

configurations {
    schemaElements {
        canBeConsumed = true
        canBeResolved = false

        attributes {
            attribute(
                Usage.USAGE_ATTRIBUTE,
                objects.named(Usage, Usage.JAVA_RUNTIME)
            )
        }

        outgoing.artifact(generateSchema.flatMap { it.outputFile })
    }
}
~~~

Ví dụ này giả định GenerateSchemaTask là task type đã được định nghĩa trong build logic và có property outputFile kiểu RegularFileProperty được đánh dấu @OutputFile.

Consumer service/build.gradle:

~~~groovy
import org.gradle.api.attributes.Usage

configurations {
    schemaInput {
        canBeConsumed = false
        canBeResolved = true

        attributes {
            attribute(
                Usage.USAGE_ATTRIBUTE,
                objects.named(Usage, Usage.JAVA_RUNTIME)
            )
        }
    }
}

dependencies {
    schemaInput project(
        path: ':schema',
        configuration: 'schemaElements'
    )
}

tasks.register('inspectSchema') {
    inputs.files(configurations.schemaInput)

    doLast {
        configurations.schemaInput.files.each { file ->
            println file.absolutePath
        }
    }
}
~~~

Producer cung cấp file thông qua schemaElements. Consumer khai báo project dependency đến configuration đó. Khi resolve configuration, Gradle có thể lấy artifact do task producer tạo ra và theo dõi task dependency thông qua outgoing artifact provider.

Đây là ví dụ minh họa một contract artifact tùy chỉnh. Với hệ thống thực tế, cần thiết kế attributes phù hợp với loại dữ liệu và mục đích sử dụng, đồng thời có thể dùng type/attributes riêng nếu build cung cấp nhiều loại artifact. Không nên dùng một usage chung cho những artifact có ý nghĩa khác nhau nếu điều đó làm Gradle chọn nhầm variant.

### Trường hợp C: output là tập file hoặc thư mục

Nếu producer cung cấp nhiều file hoặc một thư mục, có thể dùng ConfigurableFileCollection, DirectoryProperty hoặc artifact directory phù hợp. Cần khai báo rõ producer của các file đó.

Ví dụ trong cùng project:

~~~groovy
tasks.register('collectReports') {
    inputs.files(tasks.named('generateReports').map { it.outputDirectory })

    doLast {
        inputs.files.files.each { println it }
    }
}
~~~

Trong task type dùng thật, nên khai báo input bằng property riêng thay vì đọc trực tiếp inputs.files nếu cần xử lý logic cụ thể. Mục đích của ví dụ là cho thấy consumer nhận output property từ producer thay vì tự đoán thư mục.

## 9. Generated source giữa các mô-đun

Một trường hợp phổ biến là mô-đun producer sinh mã Java, còn mô-đun consumer biên dịch mã đó.

Nếu code được sinh ra thuộc cùng project, có thể nối output directory của task generator vào source set:

~~~groovy
def generateSources = tasks.register('generateSources', GenerateSourcesTask) {
    outputDirectory.set(layout.buildDirectory.dir('generated/sources/main'))
}

sourceSets {
    main {
        java.srcDir(generateSources.flatMap { it.outputDirectory })
    }
}
~~~

Provider từ output directory giúp Gradle biết thư mục source được tạo bởi task nào. Compile task có thể được nối với producer để chạy generator trước khi biên dịch.

Với generated source do project khác cung cấp, nên công bố artifact/variant phù hợp từ producer. Consumer khai báo dependency vào variant đó và nối file/directory vào source set hoặc task input tương ứng.

### Tránh sinh mã vào src/main/java

Không nên mặc định ghi mã nguồn sinh tự động vào thư mục source được quản lý bằng version control. Thư mục build/generated thường phù hợp hơn vì:

- Output có thể được xóa và tạo lại.
- Không làm lẫn mã nguồn viết tay với mã được sinh.
- Gradle có thể quản lý output của task.
- Build cache và up-to-date checking có thể hoạt động khi input/output được khai báo đúng.
- Nhiều developer/CI có thể tạo output từ cùng một source tree.

Nếu output cần được commit vì một lý do cụ thể, đó là quyết định riêng của quy trình repository. Không nên để task ghi đè source file tùy tiện.

## 10. File collection và builtBy

Đôi khi producer cung cấp file collection không nằm trong một property đơn lẻ. Gradle hỗ trợ builtBy để gắn thông tin task tạo file với file collection.

Ví dụ:

~~~groovy
def generatedFiles = files(
    layout.buildDirectory.file('generated/report.json')
).builtBy(tasks.named('generateReport'))

tasks.register('consumeReport') {
    inputs.files(generatedFiles)

    doLast {
        generatedFiles.each { file ->
            println file.text
        }
    }
}
~~~

builtBy khai báo task nào tạo ra các file trong collection. Khi collection được dùng làm input của task consumer, Gradle có thể đưa producer vào graph.

Tuy nhiên, nếu task đã có RegularFileProperty hoặc DirectoryProperty làm output, việc truyền trực tiếp provider từ task thường rõ ràng hơn. Dùng builtBy khi cần mô tả producer cho một file collection được tạo từ các file/path khác.

### builtBy không tạo file

builtBy chỉ khai báo quan hệ build. Nó không thực hiện công việc ghi file và không thay thế output property của task producer. Producer vẫn cần có action tạo đúng file ở vị trí được khai báo.

Nếu task producer không tạo file như đã cam kết, consumer vẫn có thể thất bại khi đọc input.

## 11. Tổ chức contract artifact bằng configuration

Khi một mô-đun cần cung cấp loại output không phải Java library, configuration consumable là một cách tạo contract giữa producer và consumer.

Một configuration thường có các thuộc tính vai trò:

| Thuộc tính | Ý nghĩa |
|---|---|
| canBeConsumed | Project khác có thể lấy artifact từ configuration này không? |
| canBeResolved | Configuration có thể được resolve thành file/dependency graph không? |
| canBeDeclaredAgainst | Có thể khai báo dependency trực tiếp vào configuration này không? |
| attributes | Mô tả variant để chọn đúng producer/consumer |
| outgoing.artifact(...) | Công bố artifact mà producer cung cấp |
| extendsFrom | Kế thừa dependency từ configuration khác |

Với configuration chỉ cung cấp artifact:

~~~groovy
configurations {
    reportsElements {
        canBeConsumed = true
        canBeResolved = false
    }
}
~~~

Với configuration chỉ resolve artifact từ project khác:

~~~groovy
configurations {
    reportsInput {
        canBeConsumed = false
        canBeResolved = true
    }
}
~~~

Không nên dùng một configuration vừa khai báo dependency, vừa resolve và vừa công bố artifact cho mọi mục đích. Tách vai trò giúp build model dễ hiểu và giảm việc resolve nhầm configuration.

### Attributes giúp phân biệt loại artifact

Nếu producer cung cấp nhiều variant, consumer cần khai báo attributes phản ánh nhu cầu. Ví dụ, hai variant có thể cùng là file ZIP nhưng một variant là distribution để triển khai, còn variant kia là archive chứa test fixture. Chỉ dựa vào phần mở rộng .zip là không đủ để chọn đúng.

Có thể định nghĩa custom attribute cho một loại artifact riêng. Khi đó producer và consumer phải dùng cùng attribute name/type và giá trị tương thích. Việc chọn variant sẽ dựa trên metadata thay vì tên file hoặc vị trí thư mục.

### Không dùng configuration nội bộ như API ổn định cho consumer

Configuration có thể là implementation detail. Chỉ công bố configuration mà project khác thực sự cần tiêu thụ. Đặt tên thể hiện rõ nội dung/contract, mô tả attributes và giữ output ổn định về ý nghĩa.

## 12. Quan hệ giữa project dependency và task dependency

Hai loại dependency có thể kết nối nhau nhưng giải quyết câu hỏi khác nhau.

| Câu hỏi | Cơ chế |
|---|---|
| :app cần thư viện do :domain cung cấp | Project dependency |
| :domain cung cấp compile/runtime variant nào | Outgoing variants và attributes |
| Task compileJava cần output nào | Task input/classpath |
| Task generateSchema tạo file nào | Task output property |
| Task inspectSchema cần file do generator tạo | Provider output nối vào task input |
| Một task phải chạy sau task khác nhưng không dùng output trực tiếp | dependsOn hoặc ordering rule phù hợp |

Ví dụ:

~~~groovy
dependencies {
    implementation project(':domain')
}
~~~

mô tả dependency component. Còn:

~~~groovy
tasks.register('packageDomain') {
    dependsOn project(':domain').tasks.named('jar')
}
~~~

mô tả task dependency tường minh. Trong hầu hết trường hợp sử dụng thư viện Java, không cần tự nối jar như đoạn thứ hai; project dependency đã cho Gradle biết component cần được resolve và build.

Truy cập trực tiếp task của project khác để ghép workflow thường làm tăng coupling giữa các project. Hãy ưu tiên project dependency và variant nếu consumer cần component; dùng task output provider khi cần output cụ thể; chỉ dùng task dependency trực tiếp cho quan hệ điều phối có chủ đích.

## 13. Tránh truy cập task của project khác bằng đường dẫn và cấu hình chéo

Một anti-pattern khác là consumer truy cập model task của producer trong lúc cấu hình:

~~~groovy
// Ví dụ không nên dùng làm cách nối dữ liệu thông thường
def producerTask = project(':domain').tasks.named('generateMetadata')
~~~

Việc truy cập task của project khác có thể làm cấu hình build phụ thuộc thứ tự project evaluation, tăng coupling và gây khó khăn cho configuration cache hoặc project isolation.

Khi cần chia sẻ output qua ranh giới project, hãy công bố artifact qua outgoing configuration/variant và để consumer khai báo dependency. Producer sở hữu task và output; consumer chỉ sử dụng contract đã công bố.

### Tránh afterEvaluate và evaluationDependsOn để sửa lỗi wiring

Các cách như afterEvaluate hoặc evaluationDependsOn đôi khi được thêm vào để buộc project khác được cấu hình trước. Chúng thường che giấu vấn đề về mô hình dependency hoặc provider.

Nếu consumer cần artifact của producer, project dependency hoặc configuration consumable thường diễn đạt đúng nhu cầu hơn. Nếu task cần output task khác, dùng provider output. Chỉ dùng điều khiển evaluation order khi có lý do đặc biệt và hiểu rõ ảnh hưởng đến cấu hình build.

## 14. Build cache và up-to-date checking phụ thuộc input/output rõ ràng

Gradle chỉ có thể xác định một task có cần chạy lại hay không khi biết dữ liệu nào ảnh hưởng đến kết quả và output nào được tạo.

Một task producer nên khai báo:

- Input file/directory/value ảnh hưởng đến kết quả.
- Output file/directory được tạo.
- Toolchain hoặc classpath cần thiết nếu chúng ảnh hưởng kết quả.
- Những tham số môi trường có ảnh hưởng đến output theo cách phù hợp.

Ví dụ:

~~~groovy
abstract class GenerateIndex extends DefaultTask {
    @InputDirectory
    abstract DirectoryProperty getSourceDirectory()

    @OutputFile
    abstract RegularFileProperty getIndexFile()

    @TaskAction
    void generate() {
        def source = sourceDirectory.get().asFile
        def destination = indexFile.get().asFile

        destination.parentFile.mkdirs()
        def names = source.listFiles()
            .findAll { it.isFile() }
            .collect { it.name }
            .sort()

        destination.text = names.join(System.lineSeparator())
    }
}
~~~

Consumer nhận indexFile qua provider. Khi source input thay đổi, Gradle có thể xác định producer cần chạy lại. Khi output vẫn hợp lệ, Gradle có thể đánh dấu task UP-TO-DATE hoặc khôi phục output từ build cache nếu task được cấu hình cacheable và đáp ứng các điều kiện liên quan.

Nếu consumer tự đọc một đường dẫn hard-code mà không khai báo input, Gradle có thể không biết file đó ảnh hưởng đến kết quả. Task có thể bị bỏ qua không đúng lúc hoặc cache output không an toàn.

### Output cần ổn định và nằm trong vùng sở hữu

Producer nên ghi output vào thư mục build của chính nó, trừ khi có lý do rõ ràng để công bố một vị trí khác. Không nên ghi vào thư mục build của project khác hoặc source tree của consumer.

Quyền sở hữu rõ ràng giúp:

- clean của producer quản lý đúng output.
- Output không bị hai project ghi đè.
- Task có thể chạy song song khi không có xung đột.
- Cache có thể lưu/khôi phục output theo task.
- Consumer chỉ nhận dữ liệu đã được producer công bố.

## 15. Đầu ra giữa các mô-đun trong CI

Build local có thể vô tình thành công nhờ output cũ còn nằm trên disk. CI runner sạch thường làm lộ các dependency vào file path thủ công.

Một pipeline nhiều mô-đun nên có thể build từ trạng thái checkout sạch:

~~~text
CI checkout
    |
    v
Gradle Wrapper
    |
    v
Resolve project dependencies
    |
    v
Build producer outputs
    |
    v
Build consumer modules
    |
    v
Run tests
    |
    v
Package artifacts
~~~

Gradle có thể lập graph từ project dependency và task input/output. Nếu producer output được khai báo đúng, CI không cần chạy một lệnh thủ công trước chỉ để tạo file mà consumer tự tìm.

### Kiểm tra bằng cách chạy consumer từ trạng thái sạch

Một cách kiểm tra hữu ích là xóa output của project theo quy trình build thông thường rồi gọi task consumer trực tiếp:

~~~shell
./gradlew clean
./gradlew :app:compileJava
~~~

Nếu :app cần :domain, Gradle phải xây dựng dependency cần thiết. Nếu consumer đọc một file được sinh từ project khác, task graph phải chứa producer task thông qua project dependency hoặc output provider/variant.

Không cần chạy QA nội dung khi đang viết bài; đây là quy trình kỹ thuật mà maintainer có thể dùng để xác minh wiring trong repository thực tế.

### Không phụ thuộc thứ tự lệnh CI bên ngoài nếu dependency thuộc build

Một pipeline có thể viết:

~~~shell
./gradlew :domain:generateMetadata
./gradlew :app:consumeMetadata
~~~

Cách này có thể hoạt động, nhưng nó làm orchestration bên ngoài chịu trách nhiệm giữ đúng thứ tự. Nếu người khác gọi riêng :app:consumeMetadata, producer có thể chưa chạy.

Khi dependency là một phần của build model, hãy biểu diễn nó trong Gradle. CI chỉ cần gọi mục tiêu mong muốn; Gradle sẽ xây dựng graph phù hợp.

## 16. Included build và artifact từ build khác

Project dependency project(':domain') dùng cho các project thuộc cùng một Gradle build. Khi code được tổ chức thành một included build hoặc build độc lập, cách tiêu thụ có thể khác.

### Included build

Included build được kết nối trong settings:

~~~groovy
includeBuild('build-logic')
~~~

Included build vẫn là một build riêng có settings, project model và lifecycle riêng. Gradle có thể kết nối component giữa các build qua composite build substitution hoặc plugin management theo cấu hình.

Không nên giả định project path của included build luôn giống project path của root build. Hãy sử dụng cơ chế composite build và dependency coordinates/variant mà Gradle hỗ trợ.

### Build độc lập và artifact từ repository

Nếu producer và consumer được build độc lập, producer có thể publish artifact vào Maven/Ivy repository hoặc một repository nội bộ. Consumer khai báo module dependency theo tọa độ:

~~~groovy
dependencies {
    implementation 'com.example:domain-library:2.0'
}
~~~

Gradle resolve artifact và metadata từ repository. Consumer không cần biết thư mục checkout của producer hoặc nơi producer đã chạy build.

Đây là ranh giới phù hợp khi các mô-đun có vòng đời phát hành độc lập hoặc được dùng bởi nhiều repository.

## 17. Ví dụ tổng hợp: schema producer và service consumer

Giả sử repository có hai project:

~~~text
platform/
  settings.gradle
  schema/
    build.gradle
    src/main/...
  service/
    build.gradle
    src/main/...
~~~

**:schema** tạo file schema JSON. **:service** cần file đó để tạo code hoặc kiểm tra cấu hình.

### Producer sở hữu task

schema/build.gradle:

~~~groovy
def generateSchema = tasks.register('generateSchema', GenerateSchemaTask) {
    inputDirectory.set(layout.projectDirectory.dir('src/main/schema'))
    outputFile.set(layout.buildDirectory.file('generated/schema.json'))
}
~~~

Task type GenerateSchemaTask khai báo input directory và output file bằng managed properties.

### Producer công bố artifact

~~~groovy
configurations {
    schemaElements {
        canBeConsumed = true
        canBeResolved = false
        outgoing.artifact(generateSchema.flatMap { it.outputFile })
    }
}
~~~

Nếu build có nhiều loại schema hoặc nhiều mục đích tiêu thụ, bổ sung attributes để phân biệt các variant.

### Consumer khai báo dependency

service/build.gradle:

~~~groovy
configurations {
    schemaInput {
        canBeConsumed = false
        canBeResolved = true
    }
}

dependencies {
    schemaInput project(
        path: ':schema',
        configuration: 'schemaElements'
    )
}
~~~

Task consumer dùng configuration làm input:

~~~groovy
tasks.register('validateSchema') {
    inputs.files(configurations.schemaInput)

    doLast {
        configurations.schemaInput.files.each { file ->
            println 'Validating ' + file.name
        }
    }
}
~~~

Khi validateSchema resolve schemaInput, Gradle có thể lấy artifact từ producer và thực hiện task tạo output cần thiết. Consumer không cần biết file nằm ở schema/build/generated/schema.json.

Đây là ví dụ về custom artifact contract. Nếu schema chỉ được dùng bên trong cùng project, có thể nối task output provider trực tiếp. Nếu schema là API được nhiều project tiêu thụ, outgoing configuration với attributes tạo ranh giới rõ ràng hơn.

## 18. Những nhầm lẫn thường gặp

| Dễ nhầm | Cách hiểu đúng |
|---|---|
| Project dependency và đường dẫn đến JAR giống nhau | Project dependency cung cấp component, variant và quan hệ build; file path chỉ trỏ đến vị trí |
| dependsOn tự truyền file output | Nó thiết lập dependency thực thi; consumer vẫn cần nhận file qua input/provider hoặc file collection |
| mustRunAfter bảo đảm producer chạy | Nó chỉ sắp xếp thứ tự nếu cả hai task đã được chọn |
| File tồn tại trên máy nghĩa task graph đúng | File có thể là output cũ từ lần build trước |
| Tên JAR của producer là contract | Contract nên là project component hoặc outgoing artifact/variant |
| project(':domain') phụ thuộc vào thư mục vật lý | Project path được settings ánh xạ đến project directory |
| apiElements và runtimeElements là task | Đây là outgoing configurations/variants |
| Mọi output đều phải là JAR | Output có thể là file, directory, archive, generated source hoặc metadata |
| Provider chỉ là một cách viết path ngắn hơn | Provider có thể mang thông tin về producer và trì hoãn việc tính giá trị |
| builtBy tạo ra output | Nó khai báo task tạo file; task action vẫn phải tạo file |
| Đọc task của project khác là cách tốt nhất để chia sẻ output | Nên công bố component/variant hoặc nối task output theo contract |
| Chạy producer trước consumer trong CI thay thế dependency model | Lệnh tuần tự bên ngoài không bảo đảm consumer tự build đúng khi được gọi riêng |
| Build cache tự hiểu mọi file được đọc | Input/output phải được khai báo rõ ràng |
| Gradle multi-project build và JPMS module là cùng một khái niệm | Gradle project là đơn vị build; JPMS module là đơn vị module Java |

## 19. Quy trình thiết kế output giữa các mô-đun

Khi một mô-đun cần output từ mô-đun khác, hãy xác định theo thứ tự:

1. **Xác định producer**: project/task nào sở hữu dữ liệu và chịu trách nhiệm tạo output?
2. **Xác định loại output**: Java library, JAR, file đơn, directory, generated source, report hay distribution?
3. **Xác định consumer**: project/task nào cần output và dùng nó cho compile, runtime hay một thao tác build?
4. **Chọn contract**:
   - Java library trong cùng build: project dependency.
   - Output task trong cùng project: nối task output provider vào task input.
   - Artifact tùy chỉnh giữa các project: outgoing configuration/variant và project dependency.
   - Artifact giữa các build độc lập: publish/consume qua repository.
5. **Khai báo input/output**: producer đánh dấu output; consumer khai báo input với property/file collection phù hợp.
6. **Nối dependency**: dùng provider có producer metadata, outgoing artifact hoặc builtBy khi phù hợp.
7. **Tránh đường dẫn nội bộ**: không tự ghép ../other/build/... hoặc tên file archive do producer tạo.
8. **Kiểm tra từ trạng thái sạch**: gọi trực tiếp task consumer và quan sát graph để xác nhận producer được đưa vào.
9. **Xem xét cache và chạy song song**: bảo đảm output thuộc producer, input được khai báo và không có hai task cùng ghi một file.

Một thiết kế tốt cho phép consumer chỉ nói rõ **nó cần loại dữ liệu nào**. Producer quyết định **tạo dữ liệu đó ra sao và ở đâu**. Gradle nối hai phía bằng project dependency, variant hoặc task output provider để build vẫn đúng khi đổi layout, tên artifact, thư mục build và môi trường chạy.

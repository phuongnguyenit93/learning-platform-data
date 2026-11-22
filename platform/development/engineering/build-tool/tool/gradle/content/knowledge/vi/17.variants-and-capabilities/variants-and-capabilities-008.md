# Artifact transform và vai trò trong quá trình tiêu thụ dependency

## 1. Vấn đề mà Artifact Transform giải quyết

Một Gradle build không chỉ chọn tọa độ `group:module:version` rồi tải một file JAR. Consumer có thể muốn **dạng artifact khác** với dạng producer đang công bố: ví dụ plugin phân tích cần thư mục class thay vì JAR, công cụ kiểm toán cần báo cáo checksum hoặc công cụ tối ưu cần một JAR được biến đổi trước khi đưa vào bước tiếp theo.

**Artifact Transform** là cơ chế chuyển đổi artifact của dependency từ một bộ thuộc tính sang một bộ thuộc tính khác, khi consumer yêu cầu dạng đầu ra mà producer chưa cung cấp trực tiếp. Gradle chọn và thực thi transforms như một phần của **artifact resolution**; người dùng không phải tạo một task thủ công để chuyển từng artifact.

~~~text
Consumer requests: artifactType=sha256-report
          |
          v
Gradle resolves component + selected variant
          |
          v
Source artifact: jar
          |
          +-- No direct artifact set matches?
                   |
                   v
        Registered transform jar -> sha256-report
                   |
                   v
       Output: file report, created by Gradle work
                   |
                   v
             Consumer receives it
~~~

Điểm quan trọng: artifact transform **thay đổi artifact files được tiêu thụ**, không tự thay đổi module/version, capabilities, transitive dependencies hay API contract của producer.

### Kết quả học tập

1. Phân biệt component, variant, attribute, capability, artifact và artifact transform.
2. Hiểu cách Gradle chọn source variant, tìm transform hoặc chuỗi transforms, rồi cấp artifacts cho task.
3. Viết `TransformAction` với `@InputArtifact` và `TransformOutputs`.
4. Đăng ký transform bằng `dependencies.registerTransform`, khai báo `from`/`to` attributes.
5. Yêu cầu kết quả qua `ArtifactView` mà không phá classpath gốc.
6. Sử dụng `@CacheableTransform`, file normalization và parameters đúng hợp đồng.
7. Chẩn đoán transform không chạy, artifact không tương thích, chain mơ hồ, output và cache errors.

## 2. Component, variant, capability và artifact khác nhau

| Khái niệm | Diễn giải | Ví dụ |
| --- | --- | --- |
| Component | Module hoặc project được chọn | `org.apache.commons:commons-lang3:3.17.0` |
| Variant | Một lựa chọn producer công bố cho một mục đích | Java API, Java runtime |
| Attribute | Cặp khóa–giá trị mô tả thứ consumer cần/producer có | `org.gradle.usage=java-runtime` |
| Capability | Khả năng component/variant cung cấp; có thể tham gia giải quyết xung đột | Capability do producer khai báo |
| Artifact | File hoặc directory thực tế của variant | JAR, classes directory, ZIP |
| Transitive dependencies | Dependency được variant yêu cầu thêm | Runtime module dependencies |
| Artifact Transform | Phép đổi dạng một hay nhiều artifact outputs | JAR → directory hoặc JAR → report |
| ArtifactView | Một cách nhìn riêng lên artifacts đã resolve | `configuration.incoming.artifactView` |

Producer có thể công bố hai variants khác nhau mà **cùng trỏ vào một JAR**, nhưng khác dependency metadata. Ngược lại, một variant có thể có nhiều artifacts. Khi transform chạy, nó tạo **virtual artifact set**, thường giữ nguyên transitive dependencies của source variant. Vì vậy nó không thay thế quy tắc version resolution hay capability conflict resolution.

### 2.1. Capability không phải artifactType

`Capability` diễn đạt producer cung cấp khả năng nào. `artifactType` mô tả dạng file như `jar`, `directory` hoặc giá trị tùy chỉnh như `sha256-report`. Nếu hai modules cùng cung cấp một capability gây conflict, đăng ký transform không tự giải quyết conflict đó. Cần phân tích component metadata và capability selection đúng lớp.

### 2.2. Attributes thường gặp

| Attribute | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `org.gradle.usage` | `java-api`, `java-runtime` | Phân biệt API/Runtime |
| `org.gradle.category` | `library`, `platform` | Phân loại variants |
| `org.gradle.libraryelements` | `jar`, `classes` | Kiểu thành phần thư viện |
| `org.gradle.jvm.version` | 17, 21 | Khả năng tương thích Java/JVM |
| `artifactType` | `jar`, `sha256-report` | Kiểu artifact files được yêu cầu |
| Custom attribute | `minified=true` | Chính sách do plugin định nghĩa |

Gradle hỗ trợ attribute matching/compatibility/disambiguation, không chỉ kiểm tra chuỗi bằng nhau. Khi debug hãy xem cả **requested attributes** của consumer và **offered attributes** của producer.

## 3. Luồng tiêu thụ dependency và vị trí transform

Một cách đọc từng bước:

1. Project khai báo `implementation("g:m:v")` hoặc một configuration khác có dependency.
2. Gradle resolves version/component theo metadata, constraints và conflict rules.
3. Gradle lựa chọn producer variant tương thích requested attributes/capabilities.
4. Gradle xác định source artifact set của variant.
5. Nếu dạng artifact consumer cần không có trực tiếp, Gradle tìm transform path từ thuộc tính source sang thuộc tính target.
6. Các transform actions được thực thi khi cần để cung cấp files cho consumer.
7. Task/plugin/IDE sử dụng transformed files như nguồn đầu vào.

~~~text
Dependency request
      |
      v
Component and version resolution
      |
      v
Variant-aware selection
      |
      v
Source artifact set
      |
      +-- Directly matches request? --> Consume directly
      |
      +-- Needs different artifact format?
                      |
                      v
               Find transform chain
                |             |
                |             +-- No path/ambiguous --> ERROR
                v
           Transform outputs
                |
                v
          Consumer task or tool
~~~

**Không có quy tắc “cứ đăng ký là chạy”.** Nếu một variant/artifact set phù hợp yêu cầu có sẵn, Gradle không cần transform. Nếu chẳng có transform path hợp lệ, resolution có thể lỗi thay vì tự động chuyển file theo đuôi.

### 3.1. Phân biệt các lỗi theo lớp

- `Could not resolve module`: có thể sai repository, version, policy hoặc component resolution.
- `No matching variant`: có thể sai attributes/capabilities và producer không cung cấp variant thích hợp.
- Không tìm được artifact ở dạng yêu cầu: có thể cần transform registration đúng from/to.
- Transform thực thi nhưng không có output: `TransformAction` chưa tạo/đăng ký file đúng.
- Task nhận file nhưng không dùng được: output format hoặc compatibility contract sai.

Đừng dùng `registerTransform` như cách chữa mọi lỗi dependency resolution.

## 4. Khi nào nên dùng Artifact Transform?

| Nhu cầu | Giải pháp phù hợp |
| --- | --- |
| Consumer cần classes directory từ JAR | Artifact transform unzip an toàn, nếu không có dạng phù hợp sẵn |
| Công cụ phân tích cần report theo từng JAR dependency | Artifact transform hoặc API/plugin chuyên dụng |
| Cần minify/relocate JAR trước khi một tool tiêu thụ | Transform của plugin đáng tin, kiểm thử bytecode kỹ |
| Cần đổi ZIP thành directory tại boundary dependency | Artifact transform nếu thật sự tiêu thụ dependency |
| Copy file nguồn project sang `build/output` | Dùng task `Copy`, không cần transform |
| Sinh Java source từ schema nằm trong project | Dùng custom task type/code generation plugin |
| Chọn version dependency khác | Constraints, substitution hoặc resolution policy |
| Consumer cần Java runtime variant thay vì Java API variant | Variant-aware resolution, chưa cần custom transform |
| Publish file ZIP/JAR do project xây | Task archive/publishing plugin |
| Xác minh checksum hoặc signature nguồn tin cậy | Gradle Dependency Verification, không chỉ tự tính hash |

Một transform tốt hoạt động theo nguyên tắc **một input artifact → kết quả có thể xác định từ inputs/parameters**, không có network side effects, không ghi file ngoài output Gradle quản lý và không làm lộ dữ liệu nhạy cảm.

## 5. Ba thành phần bắt buộc trong một transform

### 5.1. Action type

Mẫu Kotlin DSL:

~~~kotlin
import org.gradle.api.artifacts.transform.InputArtifact
import org.gradle.api.artifacts.transform.TransformAction
import org.gradle.api.artifacts.transform.TransformOutputs
import org.gradle.api.artifacts.transform.TransformParameters
import org.gradle.api.file.FileSystemLocation
import org.gradle.api.provider.Provider

abstract class NameReportTransform :
    TransformAction<TransformParameters.None> {

    @get:InputArtifact
    abstract val inputArtifact: Provider<FileSystemLocation>

    override fun transform(outputs: TransformOutputs) {
        val file = inputArtifact.get().asFile
        outputs.file("file-name.txt").writeText(
            file.name + "\n",
            Charsets.UTF_8
        )
    }
}
~~~

- `TransformAction<TransformParameters.None>` dành cho transform không có parameters.
- `@get:InputArtifact` yêu cầu Gradle inject input artifact vào getter.
- Kiểu getter chuẩn là `Provider<FileSystemLocation>`.
- `transform(outputs)` là method thực hiện công việc; không phải Gradle task có tên riêng.
- `outputs.file(relativeName)` cấp đường dẫn để action tạo file; file phải tồn tại khi action kết thúc.

### 5.2. Registration

Ví dụ chỉ minh họa cặp thuộc tính:

~~~kotlin
dependencies {
    registerTransform(NameReportTransform::class) {
        from.attribute(
            ArtifactTypeDefinition.ARTIFACT_TYPE_ATTRIBUTE,
            "jar"
        )
        to.attribute(
            ArtifactTypeDefinition.ARTIFACT_TYPE_ATTRIBUTE,
            "name-report"
        )
    }
}
~~~

Để dùng được, script phải có import `org.gradle.api.artifacts.type.ArtifactTypeDefinition` và consumer yêu cầu artifact type `name-report`. Registration không có nghĩa lập tức chuyển mọi JAR.

### 5.3. Consumer request

Ví dụ snippet cần configuration `runtimeClasspath`:

~~~kotlin
val reports = configurations.named("runtimeClasspath").get()
    .incoming.artifactView {
        attributes {
            attribute(
                ArtifactTypeDefinition.ARTIFACT_TYPE_ATTRIBUTE,
                "name-report"
            )
        }
    }.files
~~~

`ArtifactView` cung cấp một `FileCollection` theo requested artifact attributes. Nó không phải một configuration dependency declaration mới, và cũng không tự thêm module vào graph. Khi task thực sự cần files, Gradle sẽ giải quyết yêu cầu tương ứng.

## 6. Ví dụ chạy được: JAR → báo cáo SHA-256

Ví dụ này xử lý một dependency JAR thành file text chứa SHA-256. Nó minh họa thực tế việc chuyển artifact form và tiêu thụ qua `ArtifactView`, nhưng **không thay thế** Dependency Verification vì một hash tự tính không chứng minh source đáng tin.

### 6.1. Cấu trúc và điều kiện chạy

~~~text
artifact-transform-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
└── gradle/wrapper/...
~~~

Yêu cầu Gradle Wrapper hợp lệ, JDK tương thích (JDK 17+ trong ví dụ) và kết nối Maven Central hoặc một mirror hợp lệ. Không cần Java source file vì mục tiêu chỉ là transform một external dependency.

`settings.gradle.kts`:

~~~kotlin
rootProject.name = "artifact-transform-demo"
~~~

### 6.2. Nội dung đầy đủ build.gradle.kts

~~~kotlin
import org.gradle.api.artifacts.transform.CacheableTransform
import org.gradle.api.artifacts.transform.InputArtifact
import org.gradle.api.artifacts.transform.TransformAction
import org.gradle.api.artifacts.transform.TransformOutputs
import org.gradle.api.artifacts.transform.TransformParameters
import org.gradle.api.artifacts.type.ArtifactTypeDefinition
import org.gradle.api.file.FileSystemLocation
import org.gradle.api.provider.Provider
import org.gradle.api.tasks.Copy
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import java.security.MessageDigest

plugins {
    java
}

repositories {
    mavenCentral()
}

@CacheableTransform
abstract class JarSha256Transform :
    TransformAction<TransformParameters.None> {

    @get:InputArtifact
    @get:PathSensitive(PathSensitivity.NAME_ONLY)
    abstract val inputArtifact: Provider<FileSystemLocation>

    override fun transform(outputs: TransformOutputs) {
        val source = inputArtifact.get().asFile
        val digest = MessageDigest.getInstance("SHA-256")

        source.inputStream().buffered().use { stream ->
            val buffer = ByteArray(8192)
            while (true) {
                val count = stream.read(buffer)
                if (count == -1) break
                digest.update(buffer, 0, count)
            }
        }

        val hex = digest.digest().joinToString("") { b ->
            "%02x".format(b.toInt() and 0xff)
        }

        val report = outputs.file(source.name + ".sha256")
        report.writeText(
            hex + "  " + source.name + "\n",
            Charsets.UTF_8
        )
    }
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")

    registerTransform(JarSha256Transform::class) {
        from.attribute(
            ArtifactTypeDefinition.ARTIFACT_TYPE_ATTRIBUTE,
            ArtifactTypeDefinition.JAR_TYPE
        )
        to.attribute(
            ArtifactTypeDefinition.ARTIFACT_TYPE_ATTRIBUTE,
            "sha256-report"
        )
    }
}

val reportFiles = configurations.named("runtimeClasspath").get()
    .incoming.artifactView {
        attributes {
            attribute(
                ArtifactTypeDefinition.ARTIFACT_TYPE_ATTRIBUTE,
                "sha256-report"
            )
        }
    }.files

tasks.register<Copy>("stageSha256Reports") {
    group = "verification"
    description = "Stage SHA-256 reports of dependency JARs"
    from(reportFiles)
    into(layout.buildDirectory.dir("dependency-sha256"))
}
~~~

**Hợp đồng được bảo đảm bởi mã:**

- Gradle có JAR dependency do `implementation(...)` khai báo.
- `@InputArtifact` inject input JAR vào transform.
- `@CacheableTransform` cho phép lưu/reuse kết quả khi đủ điều kiện Build Cache.
- `@PathSensitive(PathSensitivity.NAME_ONLY)` khai báo phụ thuộc tên file; vì tên nguồn được dùng trong output, không thể tùy tiện bỏ ảnh hưởng của file name.
- `MessageDigest` đọc toàn bộ bytes JAR và tạo chuỗi SHA-256 ở hệ 16.
- `outputs.file(...)` đăng ký file text, sau đó `writeText` tạo nội dung thực.
- Registration nối `artifactType=jar` với `artifactType=sha256-report`.
- `ArtifactView` yêu cầu type đích, còn `Copy` đưa kết quả vào build directory.

Không sửa JAR nguồn; file được tạo riêng trong vùng Gradle quản lý. Không ghi network/credentials vào transform action.

### 6.3. Chạy

Linux/macOS:

~~~bash
./gradlew stageSha256Reports --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat stageSha256Reports --console=plain
~~~

Khi dependency có thể giải quyết thành công và build directory giữ mặc định, file kết quả dự kiến:

~~~text
build/dependency-sha256/commons-lang3-3.17.0.jar.sha256
~~~

Nội dung file có cấu trúc:

~~~text
<64 hexadecimal characters>  commons-lang3-3.17.0.jar
~~~

Đây là **mô tả định dạng**, không phải chuỗi SHA-256 thực tế. Mã hash phải được tính từ JAR đã lấy; không được bịa giá trị hex. Task không có `println` nên Gradle có thể in tên task/trạng thái nhưng không tự in mã hash lên stdout.

Kiểm tra bằng công cụ hệ điều hành:

~~~bash
cat build/dependency-sha256/commons-lang3-3.17.0.jar.sha256
~~~

~~~powershell
Get-Content build/dependency-sha256/commons-lang3-3.17.0.jar.sha256
~~~

### 6.4. Vì sao chọn Apache Commons Lang?

Đây là một JAR Maven Central thông dụng và chỉ dùng để minh họa resolution. Nếu repository hoặc phiên bản không còn khả dụng, cần dùng dependency thật phù hợp môi trường; không nên cho rằng lỗi network là lỗi transform. Mục tiêu học tập không phụ thuộc API Java của thư viện.

### 6.5. Vì sao không đổi toàn bộ runtimeClasspath?

`runtimeClasspath` được Java plugin thiết kế để cấp những JAR/classes cần khi chạy ứng dụng. Nếu bạn chỉnh trực tiếp requested `artifactType` của toàn bộ configuration thành `sha256-report`, các task cần JAR có thể nhận file text sai dạng. `ArtifactView` tạo một **lối nhìn riêng** cho task `stageSha256Reports` mà không phá mục đích runtimeClasspath thông thường.

### 6.6. Lazy resolution

`configurations.named("runtimeClasspath").get()` chỉ lấy đối tượng configuration được đăng ký. `ArtifactView.files` là `FileCollection` được truyền trực tiếp vào `Copy.from(...)`; không gọi `.files.files` trong configuration phase để ép tải toàn bộ dependency trước khi task chạy.

## 7. Transform không phải task thông thường

| Tiêu chí | Artifact Transform | Gradle task |
| --- | --- | --- |
| API | `TransformAction.transform` | `@TaskAction`, `doLast` |
| Kích hoạt | Artifact resolution cần output format | Task graph được yêu cầu |
| Input | `@InputArtifact`, parameters/dependency artifacts | Task inputs qua annotations/properties |
| Output | `TransformOutputs.file/dir` | `@OutputFile`, `@OutputDirectory` hoặc task type |
| Đăng ký | `dependencies.registerTransform` | `tasks.register` |
| Metadata lựa chọn | `from`/`to` attributes | Task dependencies/selection |
| Cacheability | `@CacheableTransform` | `@CacheableTask` nếu phù hợp |
| Mục đích | Chuyển dạng artifact của dependency | Công việc build riêng |

Một transform **không tự có task name** để gọi bằng `./gradlew JarSha256Transform`. Thay vào đó, lệnh Gradle kích hoạt một task cần artifacts; Gradle giải quyết dependency và quyết định transform nào cần chạy.

Chạy `./gradlew help` thông thường không đủ để nói transform đã thực thi. Nếu không có consumer yêu cầu type đích, không có công việc transform tương ứng.

### 7.1. Project dependencies và external dependencies

Gradle có thể phát hiện trước transform work của project dependencies và sắp lịch phù hợp trước task tiêu thụ. Với external module dependencies, việc phát hiện artifact/transform có thể diễn ra trong lúc task thực thi cần các files. Vì vậy không đúng khi nói transform “luôn chạy trong configuration phase” hoặc “luôn chạy một lần trước mọi task”.

## 8. from/to attributes: đọc đúng chiều

Registration:

~~~kotlin
registerTransform(JarSha256Transform::class) {
    from.attribute(
        ArtifactTypeDefinition.ARTIFACT_TYPE_ATTRIBUTE, "jar"
    )
    to.attribute(
        ArtifactTypeDefinition.ARTIFACT_TYPE_ATTRIBUTE, "sha256-report"
    )
}
~~~

- **from**: điều kiện của artifact đầu vào.
- **to**: kết quả transform cung cấp.
- Các attributes đích phải có counterpart tương ứng ở phía source theo contract của Gradle.
- Có thể giới hạn `from` bằng những attributes bổ sung.
- Transform được đăng ký trong **project chứa configuration được resolve**, không tự phát tán tới mọi project của multi-project build.

Ví dụ khác có thể cần cùng lúc:

~~~text
from:
  org.gradle.libraryelements=jar
  artifactType=jar
to:
  org.gradle.libraryelements=classes
  artifactType=directory
~~~

Đây là một **mô tả attributes**, không phải mã Gradle. Khi custom transform thực sự unzip JAR, phải khai báo cặp attributes, action, outputs và validation an toàn đúng như kết quả.

### 8.1. Custom attributes

Một plugin riêng có thể tạo attribute:

~~~kotlin
import org.gradle.api.attributes.Attribute

val minified = Attribute.of(
    "com.example.minified",
    Boolean::class.javaObjectType
)
~~~

Sau đó registration có thể diễn đạt `from minified=false` → `to minified=true`. Đây là **snippet khai báo attribute**, chưa tạo transform hoặc tự bổ sung nó vào source variant. Trong multi-project build phải thống nhất key/type/compatibility rules; sai kiểu hoặc tên sẽ làm matching thất bại.

## 9. Transform chain: nối nhiều bước

Nếu producer chỉ có A và consumer cần C, Gradle có thể dùng chuỗi A→B→C nếu cả hai registrations tồn tại:

~~~text
input JAR
   |
   | transform A: jar -> extracted-directory
   v
directory
   |
   | transform B: directory -> analysis-report
   v
report
   |
   v
consumer
~~~

Một số nguyên tắc:

- Gradle tìm các transforms có thể tạo ra bộ attributes tương thích yêu cầu.
- Khi nhiều chains hợp lệ, các chains ngắn hơn thường được ưu tiên.
- Nhiều chains đồng hạng có kết quả khác nhau nhưng đều phù hợp có thể dẫn đến lỗi mơ hồ.
- Nếu nhiều chains tạo cùng bộ attributes kết quả, Gradle không bảo đảm chọn theo thứ tự khai báo.
- Không có chain hợp lệ thì resolution có thể thất bại.

**Đừng lạm dụng chuỗi dài chỉ vì có thể.** Mỗi bước thêm I/O/caching/validation và làm khó phân tích nguồn gốc output. Nếu một transform thống nhất rõ ràng hơn, cân nhắc giảm số bước.

## 10. Parameters cho transform

Khi transform cần một option ảnh hưởng output, hãy khai báo managed parameter, có annotation `@Input` phù hợp. Không capture giá trị ẩn qua environment hoặc đọc file không khai báo.

**Snippet Kotlin DSL của transform có tham số:**

~~~kotlin
import org.gradle.api.artifacts.transform.InputArtifact
import org.gradle.api.artifacts.transform.TransformAction
import org.gradle.api.artifacts.transform.TransformOutputs
import org.gradle.api.artifacts.transform.TransformParameters
import org.gradle.api.file.FileSystemLocation
import org.gradle.api.provider.Property
import org.gradle.api.provider.Provider
import org.gradle.api.tasks.Input

abstract class TaggedReportTransform :
    TransformAction<TaggedReportTransform.Parameters> {

    interface Parameters : TransformParameters {
        @get:Input
        val tag: Property<String>
    }

    @get:InputArtifact
    abstract val inputArtifact: Provider<FileSystemLocation>

    override fun transform(outputs: TransformOutputs) {
        val name = inputArtifact.get().asFile.name
        outputs.file("tagged-report.txt").writeText(
            parameters.tag.get() + ": " + name + "\n"
        )
    }
}
~~~

Registration bổ sung khi có các imports cần thiết:

~~~kotlin
dependencies {
    registerTransform(TaggedReportTransform::class) {
        from.attribute(
            ArtifactTypeDefinition.ARTIFACT_TYPE_ATTRIBUTE, "jar"
        )
        to.attribute(
            ArtifactTypeDefinition.ARTIFACT_TYPE_ATTRIBUTE, "tagged-report"
        )
        parameters {
            tag.set("dependency")
        }
    }
}
~~~

Đây là **một lựa chọn thay thế/khác** demo SHA-256, không phải phần tự chạy khi chỉ copy snippet vào file chưa khai báo imports. `tag` phải được coi là input vì đổi tag làm thay đổi file report. Với cacheable transform, ngoài `@Input` còn cần normalization cho file input và đảm bảo tính deterministic.

Nếu transform có rule file, có thể dùng `ConfigurableFileCollection`/`@InputFiles` kèm normalization. Không đọc raw file từ một đường dẫn cố định trên máy mà không đưa nó vào contract; output cache có thể sai khi dữ liệu file đổi.

## 11. @InputArtifactDependencies: chỉ dùng khi thật cần

Mặc định mỗi lượt transform có **một input artifact**. Một số thuật toán xử lý JAR (chẳng hạn class relocation) còn cần biết packages đến từ những dependencies khác. Gradle có API inject thêm dependencies của input:

~~~kotlin
@get:InputArtifactDependencies
@get:Classpath
abstract val artifactDependencies: FileCollection
~~~

Đây là **snippet trong một transform class**, không phải toàn bộ class; cần import annotations và `FileCollection`. `@Classpath` là normalization dành cho dữ liệu dạng classpath trong ví dụ.

Phần lớn transforms như checksum, đổi tên hoặc unzip một JAR **không cần** inject toàn bộ artifact dependencies. Làm vậy có thể kích hoạt thêm resolution/download, gây chậm và tăng coupling. Chỉ yêu cầu dữ liệu dependency graph khi thuật toán thật sự phụ thuộc chúng.

## 12. @CacheableTransform và normalization

`@CacheableTransform` thông báo transform có thể dùng Build Cache nếu kết quả reproducible và relocatable. Nó không có nghĩa cứ chạy một lần là mọi máy đều cache hit.

Điều kiện cần chú ý:

1. Mọi input thật sự ảnh hưởng output được khai báo: source artifact, parameters, file inputs, dependency artifacts.
2. File inputs có normalization: `@PathSensitive`, `@Classpath` hoặc annotation thích hợp.
3. Không phụ thuộc giờ hiện tại, random không kiểm soát, network response không khai báo hay absolute path của CI runner.
4. Output chỉ ghi tại đường dẫn Gradle cấp, không tạo tác dụng phụ ngoài hợp đồng.
5. Không chứa secret hoặc dữ liệu riêng tư trong Build Cache chia sẻ.

### 12.1. Chọn PathSensitivity đúng

Trong demo SHA-256:

~~~kotlin
@get:InputArtifact
@get:PathSensitive(PathSensitivity.NAME_ONLY)
abstract val inputArtifact: Provider<FileSystemLocation>
~~~

Input file **bytes** và **file name** đều ảnh hưởng report; absolute path không ảnh hưởng. Vì thế `NAME_ONLY` hợp lý hơn việc bắt Gradle so đường dẫn tuyệt đối. Nếu transform tạo output chỉ từ nội dung file và tên output cố định, có thể xem xét `NONE`, nhưng phải xác minh thuật toán thực sự không dựa vào tên hoặc relative path. Với directory trees, `RELATIVE` có thể phù hợp hơn.

**Không chọn normalization chỉ để cố tăng cache hit**. Nếu bỏ qua một đầu vào thực, cached output có thể sai.

### 12.2. Khi nào cache miss?

Cache miss có thể do source artifact đổi, parameters đổi, transform implementation đổi, normalization khác, Gradle/plugin version khác, cache chưa có kết quả hoặc cache policy không cho reuse. Nếu action không in log ở lượt hai, không có nghĩa bị bỏ qua sai: Gradle có thể reuse kết quả đã lưu.

### 12.3. Build Cache khác Configuration Cache

- **Build Cache** tái sử dụng output công việc đủ điều kiện.
- **Configuration Cache** tái sử dụng mô hình cấu hình build.

Artifact transform có thể cacheable nhưng build script vẫn vi phạm Configuration Cache nếu eager resolution hoặc truy cập Gradle APIs không phù hợp. Đừng coi hai cache là một cơ chế.

## 13. Output contract và an toàn file

`TransformOutputs.file("x.txt")` đăng ký/cấp đường dẫn output. Action phải tạo file thực, đúng định dạng, trước khi hoàn tất. `TransformOutputs.dir("dir")` tương tự với directory. Gradle quản lý output, nên không ghi ra nguồn JAR, `~/.gradle` tùy ý hoặc path tuyệt đối ngoài vùng cho phép.

Một transform có thể trả một hoặc nhiều output artifacts hoặc dùng chính input không đổi trong trường hợp API cho phép. Mỗi output cần được đăng ký; viết file ngoài danh sách output khiến Gradle khó theo dõi và cache correctness không được đảm bảo.

### 13.1. Nếu giải nén JAR: tránh Zip Slip

JAR là ZIP. Entry độc hại có thể chứa `../`, path tuyệt đối hoặc symlink; nếu ghép path trực tiếp và giải nén không kiểm tra, file có thể thoát khỏi destination. Một transform unzip nghiêm túc cần:

- normalize entry paths và kiểm tra destination vẫn nằm trong output directory;
- ngăn overwrite file ngoài output;
- kiểm soát archive bombs, số lượng entries và tổng dung lượng;
- xử lý permissions/symlink theo chính sách;
- không truy cập network hoặc ghi file nhạy cảm ngoài sandbox.

Demo SHA-256 không giải nén input, chỉ đọc bytes, nên tránh các rủi ro này. Nếu yêu cầu thực tế là kiểm tra integrity của artifact, dùng Gradle Dependency Verification và metadata đáng tin thay vì một transform tự tạo để "chứng minh" authenticity.

### 13.2. Một transform đổi JAR không tự sửa dependency metadata

Sau khi relocate/minify, binary API, resources, services và chữ ký có thể thay đổi. Nhưng metadata transitive dependencies của component không tự được viết lại. Một transform chạy thành công có thể vẫn tạo JAR làm ứng dụng lỗi runtime. Hãy có integration tests và không dùng biến đổi artifact để che xung đột component/capability.

## 14. ArtifactView: files và artifacts

ArtifactView thường có hai lối dùng:

- `.files`: trả `FileCollection` để task nhận source files.
- `.artifacts`: cho phép xem metadata của resolved artifacts và variants khi cần phân tích.

Việc truy cập files/metadata **thật sự** có thể kích hoạt resolution. Để tránh eager resolution, không viết:

~~~kotlin
// KHONG NEN trong configuration phase:
val filesNow = configurations.getByName("runtimeClasspath")
    .incoming.artifactView {
        attributes.attribute(
            ArtifactTypeDefinition.ARTIFACT_TYPE_ATTRIBUTE,
            "sha256-report"
        )
    }.files.files
~~~

Đoạn này truy cập `.files.files` và có thể yêu cầu Gradle resolve ngay khi cấu hình, kể cả lúc user chỉ chạy `help`. Thay vào đó, giữ `FileCollection` lazy, đưa cho task inputs (ví dụ `Copy.from(reportFiles)`) và để Gradle lên lịch.

`ArtifactView` cũng có thể được dùng để yêu cầu attributes khác với configuration gốc, nhưng nó **không thay thế** việc thêm dependency vào configuration. Nếu source graph trống, view không tự làm xuất hiện artifact mới.

## 15. Cách debug transform không chạy

Lần lượt xác định:

1. **Project nào** có transform registration? Với multi-project build, đăng ký trong project sẽ resolve configuration.
2. **Consumer nào** cần output type đích? Nếu không có yêu cầu thì không chạy.
3. **Source attributes** là gì? JAR có type `jar` không, hay producer trả directory/classes?
4. **Target attributes** là gì? ArtifactView có yêu cầu đúng type không?
5. Có **variant trực tiếp** thỏa requested attributes không? Nếu có, transform không cần thiết.
6. Nếu cần chain, các edges có thực sự nối được không?
7. Có hai chain cùng phù hợp gây ambiguity không?
8. Action có tạo output file/directory đã đăng ký không?
9. File output có đúng naming, extension, nội dung và semantics không?
10. Build Cache/normalization có làm reuse kết quả hoặc gây cache miss không?
11. ArtifactView đang đọc đúng resolvable configuration không?
12. Nếu task gặp lỗi, Gradle logs có phải từ transform hay thực tế là dependency repository/version chưa resolve?

### 15.1. Lệnh chẩn đoán

Với demo mục 6:

~~~bash
./gradlew artifactTransforms --console=plain
./gradlew stageSha256Reports --info --console=plain
./gradlew dependencies --configuration runtimeClasspath --console=plain
./gradlew dependencyInsight --configuration runtimeClasspath --dependency commons-lang3 --console=plain
./gradlew stageSha256Reports --build-cache --info --console=plain
~~~

Trong phiên bản Gradle có hỗ trợ, task `artifactTransforms` in các transforms đăng ký **trong project hiện tại**, gồm from/to attributes và cacheability. Nếu registration ở `:app`, dùng `./gradlew :app:artifactTransforms`; chạy ở root không mặc nhiên liệt kê đăng ký ở mọi subproject.

`dependencies` và `dependencyInsight` giúp xác định graph/version đã resolve; không thay thế việc kiểm tra file report thật. `--info`/`--debug` có thể tiết lộ metadata nội bộ hoặc secrets do plugin log, nên chỉ chia sẻ output đã redact.

### 15.2. Ma trận lỗi nhanh

| Dấu hiệu | Nguyên nhân có thể | Sửa an toàn |
| --- | --- | --- |
| Transform không chạy | Không có consumer yêu cầu target hoặc đã có direct match | Kiểm tra ArtifactView/requested attributes |
| Không tìm thấy transform path | `from`/`to` không nối hoặc thiếu registration | Kiểm tra source/target attributes |
| Ambiguous transform selection | Nhiều paths đồng hạng | Giảm registrations cạnh tranh, dùng attributes rõ |
| `@InputArtifact` lỗi | Abstract getter sai kiểu/annotation | Dùng `Provider<FileSystemLocation>` |
| File output không tồn tại | Không ghi đúng path mà `outputs.file` cấp | Tạo đủ outputs trước khi action kết thúc |
| Compile mất JAR | Đổi artifact type của runtime/compileClasspath toàn cục | Dùng ArtifactView riêng |
| Report không chính xác dù cache hit | Thiếu input/parameter hoặc normalization sai | Bổ sung hợp đồng inputs, sửa cacheability |
| Multiple filenames trùng trong staging | Nhiều transforms output cùng basename | Thiết kế naming/Copy duplicates strategy |
| Chạy lại quá nhiều | Input thay đổi, cache chưa bật, implementation đổi | Điều tra cache key và thời gian xử lý |
| ZIP unpack ảnh hưởng file ngoài output | Path traversal trong archive | Validate entry path, giới hạn output |
| Dependency resolve fail trước transform | Repository, version, TLS hoặc credentials | Khắc phục resolution trước |
| Plugin không thấy transform | Đăng ký ở project khác | Đăng ký trong consumer project |

## 16. Tình huống thực tế

**Tình huống A — Static analysis trên nhiều JAR.** Một plugin cần đọc index chuẩn hóa, còn Maven repository chỉ có JAR. Nếu việc tạo index từ từng JAR là deterministic, artifact transform giúp reuse kết quả và giữ logic ngoài producer.

**Tình huống B — Bytecode instrumentation.** Một test framework cần JAR đã instrument trước khi chạy tests. Transform có thể phù hợp, nhưng phải đảm bảo không phá classloading, service files, metadata/chữ ký; cần kiểm thử và normalization đầy đủ.

**Tình huống C — Tạo source code từ một schema trong project.** Đây thường là nhiệm vụ của custom task type vì source thuộc project và output nối vào `compileJava`. Không nên ép làm artifact transform chỉ vì cả hai đều tạo file.

**Tình huống D — Xung đột Java API/runtime variants.** Consumer muốn `java-runtime` nhưng producer chỉ có variant thuộc tính không tương thích. Trước tiên xem producer metadata và variant matching; không viết transform chỉ để né sai configuration.

**Tình huống E — Kiểm tra thư viện bị thay đổi.** Một report SHA-256 tự tính chỉ mô tả bytes input. Muốn chặn tampering, phải so với trusted checksum/signature từ Dependency Verification hay cơ chế tương đương.

## 17. Bài tập thực hành có đáp án

**Câu 1.** Producer chỉ có `artifactType=jar`, consumer muốn `artifactType=directory`. Transform có thể giúp không?  
**Đáp án:** có, nếu registration jar→directory tồn tại và output thực sự là directory phù hợp.

**Câu 2.** `registerTransform` không có consumer thì nó có tự chạy không?  
**Đáp án:** không, registration chỉ mô tả khả năng chuyển đổi.

**Câu 3.** Producer đã có artifact set đúng requested attributes. Gradle có chạy transform tùy ý không?  
**Đáp án:** không cần; direct match được ưu tiên.

**Câu 4.** Transform có tự sửa group/module/version hoặc transitive dependencies?  
**Đáp án:** không. Nó tạo artifact set mới từ source artifact.

**Câu 5.** Getter input chuẩn cần annotation/kiểu nào?  
**Đáp án:** `@InputArtifact` trên abstract `Provider<FileSystemLocation>` getter.

**Câu 6.** `outputs.file("r.txt")` có ghi nội dung file?  
**Đáp án:** không; action phải tạo file.

**Câu 7.** Trong registration JAR→report, `from` là `jar` hay `report`?  
**Đáp án:** `jar`; `to` là `report`.

**Câu 8.** Tại sao dùng ArtifactView riêng thay vì sửa runtimeClasspath?  
**Đáp án:** để giữ JAR cho các task Java trong khi task phân tích nhận report.

**Câu 9.** Có A→B và B→C, consumer yêu cầu C. Gradle có thể chọn chuỗi không?  
**Đáp án:** có nếu attributes tương thích và chain không mơ hồ.

**Câu 10.** `@CacheableTransform` đã đủ cho file input chưa?  
**Đáp án:** chưa; cần normalization thích hợp và output deterministic/relocatable.

**Câu 11.** Báo cáo SHA-256 tự sinh từ JAR có chứng minh JAR an toàn?  
**Đáp án:** không; hash phải được đối chiếu với trust metadata độc lập.

**Câu 12.** Hai modules cùng cung cấp capability xung đột. Transform jar→directory có giải quyết không?  
**Đáp án:** không; phải xử lý capability resolution.

**Câu 13.** `@InputArtifactDependencies` có luôn cần không?  
**Đáp án:** không; chỉ khi thuật toán cần artifacts từ dependency graph.

**Câu 14.** Một transform unzip archive có nguy cơ gì khi path entry chứa `../`?  
**Đáp án:** Zip Slip/path traversal; phải kiểm tra normalized destination.

**Câu 15.** Lệnh nào xem registered transforms của `:app`?  
**Đáp án:** `./gradlew :app:artifactTransforms` trên Gradle hỗ trợ.

**Câu 16.** Nên dùng custom task type hay transform để generate Java sources từ project schema?  
**Đáp án:** thường dùng custom task type và khai báo inputs/outputs.

## 18. Checklist thiết kế transform

- [ ] Nhu cầu thật sự nằm ở **artifact consumption**, không phải project task thông thường?
- [ ] Source/target attributes đã rõ ràng, không đảo from/to?
- [ ] Có direct variant đáp ứng mà không cần transform không?
- [ ] Registration nằm trong project đang resolve configuration?
- [ ] Action dùng `@InputArtifact` và output qua `TransformOutputs`?
- [ ] Output file/directory được tạo trước khi transform hoàn tất?
- [ ] Các parameters và input files được khai báo đúng?
- [ ] `@CacheableTransform` chỉ dùng khi deterministic/relocatable và có normalization?
- [ ] ArtifactView giữ nguyên classpath gốc cho consumers khác?
- [ ] Transform chain không có cạnh tranh mơ hồ?
- [ ] Có kiểm tra file output thật và kết quả build integration?
- [ ] Không ghi secrets, absolute paths hoặc dữ liệu nhạy cảm vào logs/cache?
- [ ] Nếu unzip, có bảo vệ path traversal và zip bombs?
- [ ] Với bytecode transform, có kiểm tra binary/API/resources compatibility?
- [ ] Đã xem Gradle Wrapper/API version khi áp dụng ví dụ?
- [ ] Đã phân biệt Build Cache và Configuration Cache?
- [ ] Có tránh eagerly resolving file collection trong configuration phase?

## 19. Tài liệu chính thức

- [Gradle — Artifact Transforms](https://docs.gradle.org/current/userguide/artifact_transforms.html): action, registration, chain, caching và debugging.
- [Gradle — Variant-aware Resolution](https://docs.gradle.org/current/userguide/variant_aware_resolution.html): consumer attributes và producer variants.
- [Gradle — Artifact Views](https://docs.gradle.org/current/userguide/artifact_views.html): giải quyết artifact theo requested attributes (tìm mục Artifact Views nếu tài liệu phiên bản đã tổ chức lại đường dẫn).
- [Gradle Kotlin DSL — TransformAction](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.api.artifacts.transform/-transform-action/index.html): contract action.
- [Gradle Kotlin DSL — InputArtifact](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.api.artifacts.transform/-input-artifact/index.html): getter được inject.
- [Gradle Kotlin DSL — registerTransform](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.kotlin.dsl/register-transform.html): khai báo from/to.
- [Gradle Kotlin DSL — CacheableTransform](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.api.artifacts.transform/-cacheable-transform/index.html): cacheability và normalization.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): reuse work outputs.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): bảo vệ integrity.
- [Gradle — Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): đọc resolution graph.

**Tóm tắt:** artifact transform chuyển dạng **artifact** giữa producer và consumer trong dependency resolution, được chọn theo **attributes** chứ không phải theo tên task. `TransformAction` thực thi, `TransformOutputs` công bố files, `registerTransform` định nghĩa đường from→to và `ArtifactView` thể hiện yêu cầu consumer. Nó không thay thế variant/capability selection, dependency constraints, source generation tasks hay cơ chế xác minh tính toàn vẹn dependency.
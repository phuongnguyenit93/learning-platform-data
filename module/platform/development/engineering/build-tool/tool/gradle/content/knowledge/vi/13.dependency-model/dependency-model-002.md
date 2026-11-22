# Tọa độ `group`, `name`, `version`, `classifier` và `extension` trong Gradle

## 1. Mục tiêu: biết chính xác mình đang yêu cầu module hay file nào

Khi Gradle cần thư viện từ Maven Central, repository nội bộ hoặc Ivy repository, cách khai báo phổ biến nhất là một **external module dependency** với tọa độ:

```text
group:name:version
```

Ví dụ:

```text
org.apache.commons:commons-lang3:3.14.0
```

Ba thành phần này định danh **một module ở một phiên bản**, nhưng một module có thể phát hành **nhiều artifact**: JAR chính, source JAR, Javadoc JAR, ZIP tài nguyên, AAR, POM hoặc artifact tùy chỉnh. Khi cần một file cụ thể, Gradle cho phép thêm `classifier` và/hoặc `extension`:

```text
group:name:version:classifier@extension
```

Ví dụ:

```text
org.apache.commons:commons-lang3:3.14.0:sources@jar
```

Bài học giúp bạn:

1. Giải thích đúng **group, name, version, classifier, extension** và đọc được tọa độ trong một build script.
2. Phân biệt **module/component**, **artifact file** và **metadata** (`pom.xml`, Gradle Module Metadata).
3. Dùng cú pháp string notation trong **Groovy DSL** và **Kotlin DSL**, biết khi nào cần một `classifier` hoặc `@extension`.
4. Hiểu tác dụng phụ đặc biệt quan trọng: **`@extension` kích hoạt artifact-only resolution, bỏ qua metadata và transitive dependencies**.
5. Thực hành với các artifact thật của cùng một module trên Maven Central, kiểm chứng tên file được tải.
6. Nhận diện lỗi tên artifact, classifier không tồn tại, nhầm repository, nhầm extension, và phân biệt module version với file name.

**Nguyên tắc:** nếu chỉ muốn thêm một thư viện Java bình thường, hãy bắt đầu bằng **`group:name:version`**. Chỉ chỉ định `classifier`/`extension` khi thực sự cần artifact đặc biệt và đã hiểu metadata/transitivity bị ảnh hưởng ra sao.

## 2. Giải phẫu một tọa độ

Xét ví dụ giả định:

```text
com.example.docs:manual-assets:2.4.1:vi@zip
│                │             │     │  │
│                │             │     │  └── extension = zip
│                │             │     └───── classifier = vi
│                │             └─────────── version = 2.4.1
│                └───────────────────────── name = manual-assets
└────────────────────────────────────────── group = com.example.docs
```

| Thành phần | Ý nghĩa | Ví dụ | Điểm cần nhớ |
| --- | --- | --- | --- |
| `group` | Namespace tổ chức/phát hành module; tương ứng Maven `groupId` | `org.apache.commons` | Dấu chấm trong group **không** phải separator giữa các trường tọa độ |
| `name` | Tên module; thường tương ứng Maven `artifactId` | `commons-lang3` | Không phải tên class Java, task Gradle hay thư mục nguồn |
| `version` | Version module được yêu cầu | `3.14.0` | Không phải classifier; version có thể chịu conflict resolution/constraints |
| `classifier` | Nhãn bổ sung để chọn một artifact trong cùng module/version | `sources`, `javadoc`, `tests` | Tên do **publisher** đặt; không phải mọi classifier đều tồn tại |
| `extension` | Đuôi file artifact muốn lấy | `jar`, `zip`, `aar`, `pom` | Viết sau `@`; yêu cầu trực tiếp bằng `@ext` **bỏ qua metadata** |

**Dấu phân cách:** `:` ngăn `group`, `name`, `version` và `classifier`; `@` giới thiệu `extension`. Không ghi `:jar` để chỉ extension — phần thứ tư sau dấu `:` là **classifier**. Không ghi `@sources` nếu muốn classifier `sources`, vì Gradle sẽ diễn giải `sources` là **đuôi file**.

**Đây là ví dụ cú pháp, không khẳng định artifact tồn tại:** `com.example.docs:manual-assets:2.4.1:vi@zip` chỉ giải thích cách phân tích từng trường. Để resolve được, repository phải thực sự có module/artifact tương ứng.

## 3. Bốn dạng notation và khác biệt ngữ nghĩa

| String notation | Đọc thành gì? | Gradle xử lý thế nào? |
| --- | --- | --- |
| `g:n:v` | Module `g:n`, yêu cầu version `v` | Tra metadata và chọn artifact/variant theo cấu hình consumer |
| `g:n:v:c` | Module `g:n:v`, chỉ định classifier `c` | Yêu cầu artifact có classifier; ngữ nghĩa cụ thể phụ thuộc publisher/metadata |
| `g:n:v@ext` | Artifact có đuôi `ext`, không chỉ định classifier | **Artifact-only:** bỏ qua metadata/variant/transitive dependencies |
| `g:n:v:c@ext` | Artifact có classifier `c` và đuôi `ext` | **Artifact-only:** lấy file cụ thể, bỏ qua metadata/variant/transitive dependencies |

Ví dụ thực tế từ Maven Central:

```text
org.apache.commons:commons-lang3:3.14.0
org.apache.commons:commons-lang3:3.14.0:sources
org.apache.commons:commons-lang3:3.14.0@jar
org.apache.commons:commons-lang3:3.14.0:sources@jar
org.apache.commons:commons-lang3:3.14.0@pom
```

**Bẫy quan trọng:** dòng `...:3.14.0` và `...:3.14.0@jar` **không tương đương về dependency graph**, dù trong một repository Maven thông thường cả hai có thể dẫn tới cùng tên JAR chính. Dòng có `@jar` bỏ qua việc giải thích POM/Gradle Module Metadata, vì vậy không lấy các dependency bắc cầu do metadata khai báo. Dùng `@jar` như một “thói quen cho rõ ràng” có thể làm ứng dụng thiếu thư viện lúc runtime.

**Không phải mọi dạng đều cần dùng:** classifier-only `g:n:v:sources` là cú pháp Gradle hỗ trợ để yêu cầu artifact được gắn classifier; khi cần chỉ **một file nguồn** và không muốn đi qua metadata, `g:n:v:sources@jar` nói rõ hơn mục đích artifact-only. Tuy nhiên, IDE/Gradle tooling thường có cơ chế tải sources/Javadoc riêng, nên không nhất thiết phải khai báo chúng như dependency của ứng dụng.

## 4. Module, artifact, metadata: ba khái niệm không hoán đổi

**Module (component):** `org.apache.commons:commons-lang3:3.14.0` là danh tính module phiên bản 3.14.0. Module có thể có các *variants* dùng cho compile/runtime, có thông tin dependency và có một hoặc nhiều artifact.

**Artifact:** là một file thực được phát hành. Các tên ví dụ của module trên có thể gồm:

```text
commons-lang3-3.14.0.jar
commons-lang3-3.14.0-sources.jar
commons-lang3-3.14.0-javadoc.jar
commons-lang3-3.14.0.pom
```

**Metadata:** mô tả module, các dependency/variants/artifact và các quy tắc tiêu thụ. Maven dùng `pom.xml`/file `.pom`; Gradle Module Metadata dùng `.module`; Ivy dùng `ivy.xml`. Gradle đọc metadata phù hợp để quyết định version, dependency bắc cầu, variant, capability, artifact được chọn.

Thông thường với Maven repository, một artifact theo GAV được đặt theo cây đường dẫn:

```text
<repository-root>/<group-with-dots-replaced-by-slashes>/<name>/<version>/
    <name>-<version>.pom
    <name>-<version>.jar
    <name>-<version>-<classifier>.<extension>
```

Áp dụng vào một trường hợp thật:

```text
org/apache/commons/commons-lang3/3.14.0/
    commons-lang3-3.14.0.pom
    commons-lang3-3.14.0.jar
    commons-lang3-3.14.0-sources.jar
```

Đây là **quy ước Maven repository**, không phải công thức bắt buộc cho mọi repository Ivy hoặc mọi metadata. Trong Gradle, `name` không đồng nghĩa một file name trần; classifier cũng không được tự “sáng tạo” bằng cách nối dấu gạch ngang vào tọa độ name.

### 4.1. `group` khác `package` Java và `project.group`

Ví dụ module có `group = "org.apache.commons"` nhưng class sử dụng là `org.apache.commons.lang3.StringUtils`. Tên Java package/class không phải thứ Gradle dùng để tìm JAR trong repository. Java compiler chỉ thấy class **sau khi dependency đã resolve thành file trên classpath**.

Trong project tự publish, `group` và `version` của Gradle Project có thể được dùng làm tọa độ phát hành, còn `artifactId/name` được cấu hình bởi publishing plugin/publication (thường liên hệ tên project). Nhưng khi **tiêu thụ** thư viện bên ngoài, chính tọa độ `g:n:v` khai báo trong `dependencies` xác định module đang yêu cầu; nó không tự lấy `project.group` hiện tại của ứng dụng.

### 4.2. `version` không bao hàm classifier

`3.14.0:sources` nghĩa là **version 3.14.0, classifier sources**. Nó không phải version `3.14.0-sources`. Một version có thể có nhiều artifacts. Ngược lại `3.14.0-RC1` hoặc `1.0.0-SNAPSHOT` (khi publisher dùng naming này) là **giá trị của version**, không tự tách thành classifier.

Hãy đọc tọa độ theo vị trí các dấu `:` và `@`, không đoán từ dấu `-` trong version.

## 5. Khai báo dependency thường: không cần classifier/extension

### 5.1. Groovy DSL trong `build.gradle`

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
```

Plugin `java` tạo configuration `implementation`. `mavenCentral()` xác định nơi lấy module; Gradle thường tra metadata, chọn variant/artifact phù hợp với classpath và xử lý transitive dependencies từ metadata. Đây là dạng khuyến nghị cho một Java library bình thường.

### 5.2. Kotlin DSL trong `build.gradle.kts`

```kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
```

Đây là **một file thay thế**, không dán cả Groovy và Kotlin DSL vào cùng build script. `implementation` là tên **configuration/bucket** do Java plugin tạo; nó **không phải** một phần của tọa độ `group:name:version`.

Các bucket khác như `api` (Java Library plugin), `compileOnly`, `runtimeOnly`, `testImplementation` sẽ đưa cùng một module vào **phạm vi sử dụng khác nhau**. Nếu đổi `implementation` thành `runtimeOnly`, ý nghĩa classpath thay đổi, **dù tọa độ module vẫn như cũ**.

### 5.3. Điều không nên làm

```groovy
// Sai về mục đích: dùng classifier sources làm code dependency.
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0:sources@jar'
}
```

`sources.jar` là **mã nguồn**, không phải JAR bytecode bình thường để Java compiler và runtime sử dụng. Nếu cần nguồn để IDE hiển thị, hãy dùng cơ chế IDE/Gradle tooling tải sources; nếu cần xử lý source JAR như **file dữ liệu**, tạo một configuration phù hợp thay vì đặt nó vào `implementation`.

## 6. `classifier` — chọn bản artifact phụ của cùng module

Một Maven module có thể phát hành:

- `library-1.0.jar` — JAR chính.
- `library-1.0-sources.jar` — bản source.
- `library-1.0-javadoc.jar` — tài liệu.
- `library-1.0-tests.jar` — test artifact, **nếu publisher có phát hành**.
- `library-1.0-all.jar` — bản tổng hợp, **chỉ nếu publisher dùng classifier `all`**.

Tên classifier là **dữ liệu của publisher**, không phải danh mục từ khóa có tác dụng chung cho mọi Gradle build. Ví dụ `sources` khá phổ biến, nhưng module không phát hành file đó thì Gradle vẫn báo không tìm thấy artifact. Classifier `all` không bảo đảm nội dung “fat JAR” nếu người publish không định nghĩa như vậy.

### 6.1. Đọc đúng ví dụ

```text
org.apache.commons:commons-lang3:3.14.0:sources
│                  │           │      └─ classifier
│                  │           └──────── version
│                  └──────────────────── name
└─────────────────────────────────────── group
```

Bản có extension tường minh:

```text
org.apache.commons:commons-lang3:3.14.0:sources@jar
```

Dòng thứ hai yêu cầu đúng **artifact file** với classifier `sources` và extension `jar`; do có `@jar` nên nó còn mang ngữ nghĩa **artifact-only** (bỏ qua metadata). Không nhầm với một Gradle feature variant có attributes/capabilities.

### 6.2. Khi nào classifier không phải phương án tốt nhất?

Nếu nhà phát hành mô tả **nhiều variants** bằng Gradle Module Metadata (ví dụ JVM/Android, runtime/API, platform-specific, test fixtures, feature variants), chọn variant bằng **attributes/capabilities** mới biểu đạt đúng ngữ nghĩa. Một classified JAR đơn lẻ không tự mô tả “phụ thuộc Java 17”, “chỉ chạy Android”, hoặc “cần thêm module X”; classifier giống tên file hơn là hợp đồng variant.

Ví dụ khi dùng Gradle `java-test-fixtures`, cách tiêu thụ test fixtures có thể dùng:

```kotlin
// Đoạn minh họa khi producer có công bố test-fixtures variant.
dependencies {
    testImplementation(testFixtures("com.example:lib:1.2.3"))
}
```

`com.example:lib:1.2.3` chỉ là **placeholder minh họa mô hình**, không phải artifact được xác nhận tồn tại. `testFixtures(...)` (khi plugin/variant và Gradle version hỗ trợ) cho Gradle chọn variant có metadata, thường đáng tin hơn việc đoán classifier `tests`. Không dùng đoạn này trong demo runnable ở phần 9.

## 7. `extension` và `@ext` — yêu cầu artifact theo phần mở rộng

Extension là phần sau dấu chấm của tên file xuất bản: `jar`, `zip`, `aar`, `js`, `pom`, `tar.gz` hoặc định dạng đặc thù của repository. Trong dependency notation, nó được viết sau `@`:

```text
org.example:bundle:1.2@zip
org.example:bundle:1.2:assets@zip
org.apache.commons:commons-lang3:3.14.0@jar
org.apache.commons:commons-lang3:3.14.0@pom
```

**Điều quan trọng nhất theo tài liệu Gradle:** thêm `@extension` biến yêu cầu thành **artifact-only notation**. Gradle lấy artifact theo tên/đuôi đã yêu cầu và **không tải/diễn giải module metadata** để chọn variant và dependency graph của module. Kết quả:

1. Các transitive dependencies được mô tả trong POM/Gradle Module Metadata **không được lấy tự động** cho dependency artifact-only này.
2. **Variant-aware selection** (attributes/capabilities) của module không còn hoạt động theo cách normal module dependency.
3. `@jar` **không phải cách viết dài hơn nhưng tương đương** với GAV thường.
4. Nếu artifact đó không tồn tại hoặc repository không cung cấp định dạng tương ứng, resolution sẽ fail — `@zip` không tự chuyển một JAR thành ZIP.
5. `@extension` áp dụng cho **external module dependency**; không lấy `project(":lib")@jar` hoặc `files("some.jar")@jar` làm cú pháp hợp lệ.

Ví dụ một module được publish với POM kê `dependency B`: khai báo `g:n:v` thường cho Gradle biết cần B theo metadata; khai báo `g:n:v@jar` có thể cho ra **cùng JAR của A nhưng thiếu B**. Chỉ dùng cách thứ hai nếu bạn cố ý muốn một file riêng và có cơ chế tự quản các dependency kèm theo.

### 7.1. `@pom` không có nghĩa thêm dependency quản lý phiên bản

```text
org.apache.commons:commons-lang3:3.14.0@pom
```

Cú pháp này yêu cầu **file POM như một artifact**, không phải lệnh “import dependency management” của Maven. Nếu mục tiêu là tiêu thụ một BOM quản lý version, Gradle dùng `platform("group:name:version")` hoặc `enforcedPlatform(...)` theo mô hình platform/constraints. Không thay bằng `@pom` và cho rằng các dependency của BOM đã được áp dụng.

### 7.2. `@aar` không tự tạo Android compatibility

Một AAR là định dạng Android archive. Trong Android build, nên ưu tiên sử dụng Android Gradle Plugin và module dependency thông thường để consumer nhận metadata/variants đúng. Ép `@aar` chỉ phù hợp khi bạn thật sự muốn một artifact cụ thể và biết những phần metadata bị bỏ qua. Nếu dự án Java đơn thuần nhận AAR, Gradle không tự biến nó thành JAR Java hợp lệ.

## 8. Classifier và extension ảnh hưởng tên artifact như thế nào?

Với Maven repository thông dụng, tên artifact thường có cấu trúc:

```text
<name>-<version>[-<classifier>].<extension>
```

| Requested notation | File artifact có thể được tìm |
| --- | --- |
| `org.apache.commons:commons-lang3:3.14.0` | Thường chọn `commons-lang3-3.14.0.jar` qua metadata/variant |
| `org.apache.commons:commons-lang3:3.14.0:sources` | `commons-lang3-3.14.0-sources.jar` nếu repo publish và Gradle chọn extension tương ứng |
| `org.apache.commons:commons-lang3:3.14.0@jar` | `commons-lang3-3.14.0.jar` nhưng ở artifact-only mode |
| `org.apache.commons:commons-lang3:3.14.0:sources@jar` | `commons-lang3-3.14.0-sources.jar` ở artifact-only mode |
| `org.apache.commons:commons-lang3:3.14.0@pom` | `commons-lang3-3.14.0.pom` như file artifact |

Bảng mô tả **quy ước của module Maven này**; nó không cam kết nội dung hoặc metadata của mọi repository đều theo đúng mẫu. Gradle có thể lựa chọn artifact khác nhờ Gradle Module Metadata và variant resolution khi không dùng `@extension`.

**Sai thường gặp:**

```text
org.apache.commons:commons-lang3:3.14.0:jar
```

Dòng này có **classifier là `jar`**, không phải “extension JAR”; Gradle có thể tìm `commons-lang3-3.14.0-jar.jar` nếu có cơ chế mặc định phù hợp, rồi lỗi khi artifact không tồn tại. Muốn chỉ định đuôi file, phải dùng `@jar` (và chấp nhận artifact-only), hoặc tốt hơn là **bỏ đuôi** khi dùng Java library bình thường.

## 9. Demo chạy được: lấy JAR, sources JAR và POM cùng một module

Đây là bài thực hành dùng **Groovy DSL**, không cần plugin Java/Android và không tự ghi dữ liệu lên mạng. Nó tạo ba **resolvable configurations** riêng, mỗi configuration dùng một dạng notation. Task báo cáo lấy **tên các file đã resolve** và không phụ thuộc đường dẫn cache của từng máy.

Yêu cầu: Gradle Wrapper tương thích JVM trên máy và kết nối Maven Central lần đầu (hoặc artifacts đã có trong cache). Tạo một thư mục demo độc lập:

```text
coordinates-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── gradle/
    └── wrapper/
        ├── gradle-wrapper.jar
        └── gradle-wrapper.properties
```

Nếu repository đã có Wrapper, giữ nguyên; nếu mới tạo từ số không, dùng Gradle đã cài tạm để khởi tạo Wrapper, sau đó dùng Wrapper. Không cần source Java cho demo này.

### 9.1. `settings.gradle`

```groovy
rootProject.name = 'coordinates-lab'
```

### 9.2. `build.gradle` đầy đủ

```groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

repositories {
    mavenCentral()
}

// Ba configuration độc lập; chỉ dùng để resolve artifact.
def binaryConfig = configurations.create('binaryArtifact') {
    canBeResolved = true
    canBeConsumed = false
}
def sourcesConfig = configurations.create('sourcesArtifact') {
    canBeResolved = true
    canBeConsumed = false
}
def pomConfig = configurations.create('pomArtifact') {
    canBeResolved = true
    canBeConsumed = false
}

dependencies {
    // Module dependency thông thường: đọc metadata/variant.
    add(binaryConfig.name,
        'org.apache.commons:commons-lang3:3.14.0')

    // Một artifact cụ thể: classifier sources + extension jar.
    add(sourcesConfig.name,
        'org.apache.commons:commons-lang3:3.14.0:sources@jar')

    // Một file POM như artifact, KHÔNG import BOM/dependencies.
    add(pomConfig.name,
        'org.apache.commons:commons-lang3:3.14.0@pom')
}

abstract class InspectArtifacts extends DefaultTask {
    @InputFiles
    @PathSensitive(PathSensitivity.NONE)
    abstract ConfigurableFileCollection getBinaryFiles()

    @InputFiles
    @PathSensitive(PathSensitivity.NONE)
    abstract ConfigurableFileCollection getSourceFiles()

    @InputFiles
    @PathSensitive(PathSensitivity.NONE)
    abstract ConfigurableFileCollection getPomFiles()

    @TaskAction
    void printArtifactNames() {
        def fileNames = { files ->
            files.collect { it.name }.sort().join(', ')
        }
        println('binary = ' + fileNames(binaryFiles.files))
        println('sources = ' + fileNames(sourceFiles.files))
        println('pom = ' + fileNames(pomFiles.files))
    }
}

tasks.register('inspectCoordinates', InspectArtifacts) {
    group = 'learning'
    description = 'So sánh artifact theo GAV, classifier và extension'
    binaryFiles.from(binaryConfig)
    sourceFiles.from(sourcesConfig)
    pomFiles.from(pomConfig)
}
```

**Vì sao demo dùng custom configuration?** `implementation` của Java plugin dành cho thư viện ứng dụng; một source JAR hoặc POM là **file để kiểm tra**, không nên bị đưa vào application classpath. Các configuration `binaryArtifact`/`sourcesArtifact`/`pomArtifact` được tạo riêng, đủ để tải file và so sánh notation.

**Vì sao có task type thay vì resolve file ngay khi cấu hình?** Ba `ConfigurableFileCollection` được đánh dấu `@InputFiles`; Gradle có thể xem đây là đầu vào của task trước lúc chạy action. Action chỉ đọc file names, không cố truy cập `Project`. `PathSensitivity.NONE` nói tên/path của file không phải input ảnh hưởng đến kết quả task đối với cơ chế fingerprint; trong demo chỉ in tên file nên không dùng nó làm mẫu cacheable output production. Nếu task thực sự tạo file phụ thuộc tên artifact, chọn path sensitivity phù hợp, khai báo đầy đủ output và dữ liệu liên quan.

### 9.3. Chạy trên Linux/macOS

```bash
./gradlew -q inspectCoordinates
```

Với artifacts của module được Maven Central cung cấp đúng theo ví dụ và không bị rule/repository khác thay thế, **ba dòng do task in** là:

```text
binary = commons-lang3-3.14.0.jar
sources = commons-lang3-3.14.0-sources.jar
pom = commons-lang3-3.14.0.pom
```

`-q` giảm các dòng lifecycle của Gradle; ở lần tải đầu có thể còn cảnh báo/lỗi mạng khi repository không truy cập được. Kết quả trên là **stdout logic của task** khi resolution thành công, không phải một cam kết về thời gian tải, log daemon hoặc trạng thái cache.

### 9.4. Chạy trên Windows

PowerShell:

```powershell
.\gradlew.bat -q inspectCoordinates
```

Command Prompt:

```bat
gradlew.bat -q inspectCoordinates
```

Kết quả tên file như trên; Gradle tự quản đường dẫn cache theo hệ điều hành. Đây là lý do dùng `File.name` khi quan sát artifact, không hardcode `~/.gradle/caches/...` vào script.

### 9.5. Đối chiếu graph và artifact

```bash
./gradlew dependencies --configuration binaryArtifact
./gradlew dependencies --configuration sourcesArtifact
./gradlew dependencies --configuration pomArtifact
./gradlew inspectCoordinates --info
```

Các báo cáo giúp thấy declaration/graph trong từng configuration. Để xem **file artifact nào thực sự được chọn**, task `inspectCoordinates` trực tiếp in file names; một dòng trong dependency report không luôn cho biết tên source/Javadoc/ZIP đã tải.

**Bài học từ demo:** cùng một `group:name:version` có thể cho ra **ba file khác nhau**, và `sources@jar` / `@pom` cố ý bỏ metadata. Demo dùng module không cần dependencies bắc cầu để in file names ngắn; vì thế nó **không thể tự chứng minh sự khác nhau về transitivity**. Phần 10 cung cấp ví dụ suy luận riêng về điều đó.

## 10. Tại sao `@extension` có thể gây lỗi ClassNotFoundException?

Giả sử publisher phát hành:

```text
com.example:feature-lib:1.0.0
  metadata:
    artifact = feature-lib-1.0.0.jar
    dependency = com.example:helper-lib:2.0.0

com.example:helper-lib:2.0.0
  artifact = helper-lib-2.0.0.jar
```

**Đây là mô hình giả định để giải thích transitivity**, không phải hai module đã được kiểm chứng tồn tại.

Khi khai báo module thông thường:

```groovy
dependencies {
    implementation 'com.example:feature-lib:1.0.0'
}
```

Gradle đọc metadata, nên dependency graph có thể gồm cả `feature-lib` và `helper-lib` (tùy scope, variant, rule, constraints). Nhưng nếu đổi thành:

```groovy
dependencies {
    implementation 'com.example:feature-lib:1.0.0@jar'
}
```

Gradle bỏ metadata của `feature-lib` và chỉ yêu cầu file JAR trực tiếp; `helper-lib` **không được tự kéo vào** qua metadata của `feature-lib`. Khi chạy ứng dụng, nếu code trong `feature-lib` cần class từ `helper-lib` mà classpath thiếu, có thể gặp `ClassNotFoundException` hoặc `NoClassDefFoundError`.

**Không sửa bằng cách nghĩ `isTransitive = true` sẽ đọc metadata đã bị bỏ qua**: cờ transitive không tạo ra dependency graph mà Gradle không biết. Giải pháp đúng thường là quay về **`g:n:v`**, để metadata/variant quyết định; nếu cần một artifact đặc biệt, phải hiểu và khai báo các dependency bắt buộc thông qua cơ chế phù hợp.

Đây cũng là lý do không nên “sửa tất cả JAR bằng `@jar` cho rõ ràng” trong một repository đã dùng Gradle Module Metadata.

## 11. Khi classifier không thể thay thế variant-aware resolution

Gradle hỗ trợ **variant-aware dependency resolution**. Consumer có attributes như mục đích sử dụng (`java-api` hay `java-runtime`), phiên bản JVM, loại thư viện hoặc platform. Publisher có các variants, mỗi variant có thể mang **artifact và dependency khác nhau**.

Xét một producer có hai variants:

```text
module: org.example:platform-lib:1.0
  variant java-api     -> artifact A + dependencies compile
  variant java-runtime -> artifact B + dependencies runtime
```

Đây là sơ đồ mô hình. Không thể đoán rằng thêm classifier `runtime` vào tọa độ sẽ tự chọn đúng variant `java-runtime`: classifier chỉ là nhãn trên artifact; variant attributes là **hợp đồng lựa chọn có ngữ nghĩa**.

**Nguyên tắc thực hành:**

- Với thư viện Java/Kotlin/Android đã publish metadata đúng, **không chỉ định classifier/extension** khi muốn consumer tự chọn variant.
- Với sources/Javadoc cần tra cứu, dùng IDE/tooling hoặc cấu hình riêng, không đặt source JAR lên compile/runtime classpath.
- Với một file ZIP/JS/JAR phụ không được mô tả như variant, **artifact-only** có thể phù hợp nếu không cần dependency metadata của module đó.
- Khi publisher có thể kiểm soát nội dung phát hành, ưu tiên publish **variants + artifacts + dependencies** qua Gradle Module Metadata thay vì đặt nhiều classified JAR không có metadata mô tả.
- Khi là consumer của publication cũ, có thể dùng **component metadata rules** để bổ sung thông tin còn thiếu; đây là giải pháp nâng cao, không phải sửa tên classifier ngẫu nhiên.

**Điểm cần phân biệt:** `extension=jar` mô tả dạng file; `org.gradle.libraryelements=jar` là một **attribute** trong lựa chọn variant. Hai khái niệm liên quan nhưng không thay nhau được bằng cách viết `@jar`.

## 12. `version`: yêu cầu chưa chắc là version cuối cùng được chọn

Tọa độ ghi trong script là **requested dependency**. Khi resolve một graph lớn, Gradle có thể phải chọn giữa các requested versions của cùng `group:name` do transitive dependencies, constraints, platforms, locks và các resolution rules.

Ví dụ:

```text
app -> org.example:util:1.3
app -> org.example:feature:2.0
feature -> org.example:util:1.5
```

Đây là graph **minh họa**, không phải artifacts được xác nhận tồn tại. Nếu không có constraint đặc biệt, Gradle thường có logic giải quyết conflict để chọn một version phù hợp; không được suy ra JVM classpath chắc chắn sẽ chứa **hai** file `util-1.3.jar` và `util-1.5.jar` chỉ vì graph yêu cầu cả hai.

Muốn biết **selected version** thật, chạy:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
```

Hai lệnh giả định project áp dụng plugin Java nên có `runtimeClasspath`. Đọc mũi tên/version selection reasons trong report; không chỉ dựa vào version ghi trên một dòng `implementation`.

### 12.1. Dynamic versions và reproducibility

Gradle hỗ trợ các yêu cầu version động như `1.+` hoặc `latest.release` trong những hoàn cảnh thích hợp, nhưng artifact được chọn có thể thay đổi khi repository có bản phát hành mới. `1.0-SNAPSHOT` còn có thể thay đổi bytes theo chính sách publisher/repository. Với build production/CI cần tái lập, ưu tiên version cố định, dependency locking, dependency verification và quản lý update có review.

Một version cố định **chưa bảo đảm toàn bộ graph cố định**, vì các dependency bắc cầu có thể khai báo dynamic versions, hoặc rules/constraints khác thay đổi lựa chọn. Không dùng `classifier` hay `@extension` để “khóa” version; đó là hai trường khác.

### 12.2. Version catalog không thay đổi bản chất GAV

Trong `gradle/libs.versions.toml`:

```toml
[versions]
commonsLang3 = "3.14.0"

[libraries]
commons-lang3 = { module = "org.apache.commons:commons-lang3", version.ref = "commonsLang3" }
```

Và với project Java trong `build.gradle.kts`:

```kotlin
dependencies {
    implementation(libs.commons.lang3)
}
```

Alias giúp tập trung `group/name/version`, không có nghĩa version catalog tự động bảo đảm selected version bất chấp conflict resolution. Nếu cần artifact phụ `sources@jar`, hãy cân nhắc một dependency declaration/cấu hình riêng; không giả định alias của module bình thường tự cấp classifier.

## 13. Repository là một phần của việc resolve tọa độ

`g:n:v` không chứa URL. Gradle phải tìm trong **repositories** của phạm vi dependency tương ứng. Ví dụ:

```groovy
repositories {
    mavenCentral()
}
```

Đối với Maven Central và module trong demo, Gradle sẽ tìm metadata/artifacts dưới cấu trúc Maven. Nếu company dùng repository riêng, URL và credentials phải được khai báo qua settings/project theo chính sách, không được hardcode token trong source.

Ba loại repository thường bị nhầm:

| Bạn đang tìm | Nơi định nghĩa repository | Dependency notation |
| --- | --- | --- |
| Gradle plugin qua `plugins { }` | `pluginManagement.repositories` trong settings | Plugin ID/version, không phải module dependency thông thường |
| Thư viện cho chính build script qua `buildscript { }` | `buildscript.repositories` | `classpath("g:n:v")` trong buildscript |
| Thư viện/ZIP/JAR cho project | Project `repositories { }` hoặc `dependencyResolutionManagement.repositories` trong settings | `implementation("g:n:v")`, `runtimeOnly(...)`, custom configuration |

Nếu project áp dụng `RepositoriesMode.FAIL_ON_PROJECT_REPOS` tại settings, **không thêm tùy tiện project `repositories`**; cấu hình chúng ở settings đúng chính sách. Nếu repository thứ nhất chứa metadata sai/thiếu artifact, thêm repository thứ hai không bảo đảm Gradle sẽ “trộn metadata và JAR” theo mong muốn; kiểm tra repository origin và consistency.

Gradle cache artifact, nhưng cache không tạo ra một classifier hay extension chưa từng được publisher phát hành. `--offline` không thể tải lần đầu những artifacts chưa có trong cache.

## 14. Groovy map notation và thay đổi giữa các phiên bản Gradle

Trong nhiều build script cũ, bạn có thể bắt gặp cú pháp **map notation**:

```groovy
// Legacy Groovy DSL — chỉ để đọc hiểu code cũ.
dependencies {
    implementation group: 'org.apache.commons',
                   name: 'commons-lang3',
                   version: '3.14.0'
}
```

Hoặc cú pháp có thêm khóa `classifier` / `ext` trong các DSL/API cũ. Trong cách diễn đạt này, `ext` thường là viết tắt của **artifact extension**, không phải biến `ext` dùng khai báo extra properties của project.

**Khuyến nghị hiện hành của Gradle:** dùng **single-string GAV notation**. Gradle 9.1 đã deprecate map notation cho external module dependencies và tài liệu nêu việc bỏ hỗ trợ ở Gradle 10. Vì vậy đừng chọn map notation làm phong cách mặc định cho bài tập, plugin mới hoặc khi nâng Gradle; trong Groovy nên viết:

```groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
```

Trong Kotlin DSL cũng ưu tiên:

```kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
```

**Đừng nhầm cảnh báo này với mọi named argument trong Gradle DSL:** các API khác như `exclude(group = "...", module = "...")` vẫn có quy tắc riêng. Cảnh báo đề cập **map-style external module declaration**, không cấm mọi cách truyền named arguments.

Để biết API nào hỗ trợ ở dự án thật, chạy `./gradlew --version` (không dựa vào bản Gradle toàn cục) rồi tra tài liệu đúng phiên bản Gradle Wrapper.

## 15. Các lỗi phổ biến và phương án xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm chứng/sửa |
| --- | --- | --- |
| `Could not find g:n:v` | GAV sai, version không có trên repository, repository chưa cấu hình | Kiểm tra `group/name/version`, Maven Central/private repo URL và quyền truy cập |
| Không tìm thấy `...-sources.jar` | Publisher không phát hành classifier `sources` ở version đó | Kiểm tra danh sách artifacts thật; bỏ classifier nếu muốn JAR chính |
| Lệnh `g:n:v:jar` lỗi | `jar` đang là **classifier**, không phải extension | Nếu muốn JAR thông thường dùng `g:n:v`; nếu thật sự artifact-only dùng `g:n:v@jar` |
| Lệnh `g:n:v@sources` lỗi | `sources` là extension nên Gradle tìm file `.sources` | Dùng classifier `:sources` hoặc `:sources@jar` khi có thật |
| Ứng dụng thiếu class lúc runtime sau khi thêm `@jar` | Artifact-only bỏ metadata, mất transitives | Quay về `g:n:v` để Gradle resolve metadata/graph |
| `ClassNotFoundException` sau khi thêm `sources@jar` vào `implementation` | Sources JAR không chứa bytecode cần chạy | Dùng module JAR chính, sources dùng cho tooling/đọc mã |
| `@zip` không có file | Module chỉ publish `.jar` hoặc classifier khác | Không thể đổi extension để chuyển định dạng; tìm artifact thật |
| `@pom` không import BOM | `@pom` chỉ tải POM như một file | Dùng `platform("g:n:v")` hoặc cơ chế dependency constraints |
| Máy A resolve được, máy B không | Repository access, credential, cache hoặc proxy khác nhau | Kiểm tra repositories/CI credentials, `--info` và thử môi trường sạch |
| Một dependency có version khác trong report | Conflict resolution, constraint, platform, lock | `dependencyInsight`, kiểm tra selected version và selection reasons |
| Sources JAR có, nhưng IDE không mở được | IDE tooling chưa tải sources, cấu hình IDE khác | Bật tải sources của IDE/Gradle tooling; không ép nguồn thành runtime dep |
| Gradle báo no matching variant | Attributes của consumer và producer không tương thích | Xem metadata/variants, không “sửa” bằng classifier tùy ý |
| Android app lỗi với `@aar` | Artifact-only làm mất metadata/variant/dependency hoặc thiếu Android plugin | Dùng module dependency qua Android Gradle Plugin và metadata đúng |
| Map notation warning sau nâng Gradle | Named/map external module declaration đã deprecate | Đổi sang string `"g:n:v"` theo tài liệu Wrapper |
| Dependency report không hiện tên artifact như mong đợi | Report mô tả graph, không phải từng file đã tải | Kiểm tra resolved file names qua task kiểm tra artifacts hoặc Gradle artifact reports |
| Tọa độ đúng nhưng file chứa nội dung bất ngờ | Publisher thay bytes, repository không đáng tin, conflict/metadata redirect | Kiểm tra artifact checksum, dependency verification, repository origin |
| Task Gradle plugin không tìm thấy dù có `mavenCentral()` | Plugin DSL dùng `pluginManagement` khác project repositories | Khai báo đúng plugin repositories trong settings |

**Quy trình debug gọn:**

1. Xác nhận ba trường đầu `group:name:version` có đúng với module đã publish.
2. Kiểm tra có thật sự cần `classifier` hoặc `@extension` không; thử GAV thường nếu mục tiêu là thư viện ứng dụng.
3. Xác nhận **repository đúng phạm vi** và user/CI có quyền truy cập.
4. Chạy `./gradlew dependencies --configuration ...` và `dependencyInsight` trên configuration có thể resolve; đọc version được chọn.
5. Với artifact-only, xác nhận file name thực tế trong repository và số file tải; đừng suy từ dependency report rằng classifier/extension chắc chắn tồn tại.
6. Khi nghi metadata/variant, xem Gradle Module Metadata/POM, dùng `--info` hoặc `--stacktrace` khi có lỗi phù hợp.
7. Nếu build phải tái lập, thiết lập version lock/verification thay vì chỉ tin cache trên máy cá nhân.

## 16. Bài tập tự kiểm tra

**Bài 1:** Phân tích `org.example:analytics:2.3.5:reports@zip`.

Đáp án: `group=org.example`, `name=analytics`, `version=2.3.5`, `classifier=reports`, `extension=zip`. Đây là **artifact-only** vì có `@zip`, không được tự suy ra POM transitive dependencies sẽ được đọc.

**Bài 2:** Một người viết `implementation("org.apache.commons:commons-lang3:3.14.0:jar")` và nhận lỗi không tìm thấy artifact. Sai ở đâu?

Đáp án: `jar` ở vị trí thứ tư là classifier. Đối với Java library thông thường, sửa thành `implementation("org.apache.commons:commons-lang3:3.14.0")`; không cần `@jar`.

**Bài 3:** Hai dòng sau có khác về dependency graph không?

```kotlin
implementation("org.apache.commons:commons-lang3:3.14.0")
implementation("org.apache.commons:commons-lang3:3.14.0@jar")
```

Đáp án: **Có thể khác về metadata/graph**, ngay cả khi cả hai resolve cùng tên JAR chính: dòng có `@jar` bỏ qua metadata/variant/transitives. Với mô-đun không có transitive dependencies thì file list có thể trông giống nhau, nhưng semantics không đồng nhất.

**Bài 4:** Cần chỉ tải sources JAR để phân tích mã nguồn, có nên đặt vào `implementation`?

Đáp án: không. Dùng cơ chế IDE/tooling hoặc configuration riêng với `g:n:v:sources@jar`, hiểu rằng nó là artifact-only.

**Bài 5:** Một thư viện publish ZIP `manual-2.0-fr.zip`, tọa độ module `com.example:manual:2.0`. Viết notation yêu cầu file đó.

Đáp án (khi repository thực sự có file theo quy ước Maven): `com.example:manual:2.0:fr@zip`. Không dùng `:zip` ở cuối; nhớ `@zip` bỏ metadata.

**Bài 6:** Build có `implementation("com.example:lib:1.0@pom")`. Nó có import POM BOM không?

Đáp án: không. Nó yêu cầu một POM file như artifact. Nếu cần constraint/BOM, dùng API `platform`/dependency management tương ứng.

**Bài 7:** Đã khai báo `com.example:lib:1.0` nhưng report chọn `1.2`. Vì sao?

Đáp án: có thể có conflict resolution, constraint, platform hoặc rule. Chạy `dependencyInsight` để xem nguyên nhân; không sửa bằng classifier hoặc extension.

**Bài 8:** Module publisher cung cấp variants Android và JVM với dependency khác nhau. Nên yêu cầu `:android@aar` theo tên đoán hay dùng variant-aware metadata?

Đáp án: ưu tiên **variant-aware resolution** qua plugin/attributes phù hợp. Classifier/extension chỉ là cách yêu cầu artifact file, không mô tả đầy đủ khả năng tương thích/dependencies.

## 17. Checklist trước khi commit

- [ ] Đã xác nhận `group:name:version` đúng với module thực tế và repository tương ứng.
- [ ] Chọn configuration `implementation`/`api`/`runtimeOnly`/`testImplementation` đúng theo mục đích.
- [ ] Không thêm `:sources`/`:javadoc` như thư viện runtime/compile mặc định.
- [ ] Không viết nhầm `:jar` thành extension hoặc `@sources` thành classifier.
- [ ] Nếu dùng `@extension`, đã chủ động chấp nhận **artifact-only**, không dựa vào transitive dependencies/variants của module đó.
- [ ] Nếu cần file phụ, xác minh publisher thật sự phát hành đúng classifier và extension.
- [ ] Với nhiều platform/feature/JVM variant, ưu tiên Gradle Module Metadata/attributes thay vì classifier tự đoán.
- [ ] Không dùng map-style external module dependency làm cú pháp mới trong Gradle hiện đại.
- [ ] Đã kiểm tra dependency graph/selected version bằng Gradle reports khi có conflict.
- [ ] Các phiên bản được quản lý có chủ đích; CI không phụ thuộc dynamic/SNAPSHOT ngoài chính sách.
- [ ] Plugin repository, buildscript repository và project dependency repository không bị nhầm lẫn.
- [ ] Build chạy bằng Gradle Wrapper; nếu cần tái lập mạnh, đã xem xét dependency locking/verification.

## 18. Ghi nhớ nhanh

- **`group:name:version`** = định danh một **external module** được yêu cầu.
- **`classifier`** = nhãn **artifact bổ sung** trong cùng module/version, ví dụ `sources`.
- **`extension`** = đuôi file sau `@`, ví dụ `@jar`/`@zip`/`@pom`.
- **`group:name:version:classifier@extension`** yêu cầu artifact cụ thể; **`@extension` bỏ qua metadata và transitive dependencies**.
- Một module có thể có **nhiều artifact**, và một variant có thể mô tả cả artifacts lẫn dependencies.
- `implementation`/`runtimeOnly` là **phạm vi sử dụng**, không phải một phần tọa độ.
- File name theo Maven thường là `name-version[-classifier].extension`, nhưng repository metadata/variants mới là thứ quyết định khi dùng GAV bình thường.
- Với Java/Android libraries thông thường, dùng **GAV thuần** để Gradle chọn variant đúng, chỉ định classifier/ext khi có nhu cầu thực sự.

## Tài liệu chính thức

- [Gradle — Declaring Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies_basics.html): external module dependencies, dạng `g:n:v` và `g:n:v:classifier@ext`, cảnh báo map notation.
- [Gradle — Resolving Specific Artifacts](https://docs.gradle.org/current/userguide/resolving_specific_artifacts.html): artifact-only `@extension`, classifier, hệ quả bỏ metadata/transitive dependencies.
- [Gradle — Variant-Aware Resolution](https://docs.gradle.org/current/userguide/variant_aware_resolution.html): cách Gradle chọn variant qua attributes, artifacts và dependencies.
- [Gradle — Supported Metadata Formats](https://docs.gradle.org/current/userguide/supported_metadata_formats.html): POM, Ivy và Gradle Module Metadata.
- [Gradle — Component Metadata Rules](https://docs.gradle.org/current/userguide/component_metadata_rules.html): bổ sung metadata cho classified artifacts thiếu ngữ nghĩa variant.
- [Gradle — Best Practices for Dependencies](https://docs.gradle.org/current/userguide/best_practices_dependencies.html): ưu tiên single-string notation và quản lý version.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies`, `dependencyInsight` và đọc kết quả resolution.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): cố định resolved versions cho build tái lập.

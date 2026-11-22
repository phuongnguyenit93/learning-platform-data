# Nhận diện mã nguồn, tài nguyên và cấu hình làm đầu vào build

Một build chỉ có thể tạo ra kết quả đáng tin cậy khi Gradle biết những dữ liệu nào tham gia tạo nên kết quả đó. Với một dự án Java, các dữ liệu này thường gồm mã nguồn, tài nguyên, tệp cấu hình, dependency, phiên bản công cụ và một số giá trị môi trường. Nếu bỏ sót một đầu vào, build có thể không chạy lại khi dữ liệu thay đổi, tạo artifact cũ hoặc cho kết quả khác nhau giữa máy lập trình viên và CI.

Vì vậy, trước khi tối ưu build hoặc viết custom task, cần nhận diện đúng **đầu vào build (build inputs)**. Đây là những dữ liệu có ảnh hưởng đến việc Gradle cấu hình build, thực thi task hoặc tạo artifact. Mỗi loại đầu vào có vị trí, vai trò và cách theo dõi khác nhau.

## 1. Đầu vào build là gì?

Đầu vào build là dữ liệu mà quá trình build đọc hoặc sử dụng để quyết định công việc cần thực hiện và tạo ra kết quả. Có thể chia chúng thành hai nhóm lớn:

- **Đầu vào cấu hình build:** ảnh hưởng đến cách Gradle cấu hình project, đăng ký task, tạo task graph, chọn plugin, dependency, toolchain hoặc quy tắc build.
- **Đầu vào của task:** dữ liệu mà một task cụ thể đọc để thực hiện công việc và tạo output.

Hai nhóm có liên hệ với nhau nhưng không hoàn toàn giống nhau. Ví dụ, `build.gradle` có thể cấu hình task `compileJava`, source set và dependency. Đây là đầu vào cấu hình. Những tệp `.java` trong source directory là đầu vào trực tiếp của task biên dịch. Gradle cần theo dõi cả cấu hình lẫn dữ liệu nguồn để quyết định build phải làm gì.

Một ví dụ đơn giản:

```text
Mã nguồn Java ───────────────┐
Tài nguyên ──────────────────┤
Dependency ──────────────────┤
JDK / compiler options ──────┼──> Gradle tasks ───> class files / JAR
Build scripts / properties ─┤
Gradle và plugin versions ───┘
```

Đầu vào không chỉ là tệp nằm trong `src/`. Một giá trị cấu hình, một dependency đã khai báo, phiên bản JDK hoặc một biến môi trường cũng có thể ảnh hưởng kết quả build.

## 2. Mã nguồn là đầu vào trực tiếp của quá trình biên dịch

Trong một dự án Java thông thường, mã nguồn chính nằm trong `src/main/java`, còn mã nguồn kiểm thử nằm trong `src/test/java`.

```text
project/
├── src/
│   ├── main/
│   │   └── java/
│   │       └── com/example/
│   │           └── App.java
│   └── test/
│       └── java/
│           └── com/example/
│               └── AppTest.java
├── build.gradle
└── settings.gradle
```

Java Plugin tạo các source set mặc định:

- `main` chứa mã nguồn và tài nguyên dùng để tạo ứng dụng hoặc thư viện chính.
- `test` chứa mã nguồn và tài nguyên phục vụ kiểm thử, đồng thời sử dụng output và dependency phù hợp của source set chính.

Các tệp `.java` trong source directory là đầu vào của task biên dịch tương ứng. Khi một tệp nguồn thay đổi, Gradle có thể xác định task biên dịch cần thực hiện lại. Với incremental compilation, compiler và Gradle có thể giới hạn phạm vi biên dịch lại tùy loại thay đổi và quan hệ giữa các lớp.

Không phải mọi tệp trong repository đều là mã nguồn Java. Markdown, ảnh, tệp cấu hình ứng dụng hoặc SQL thường là tài nguyên hay dữ liệu khác. Đặt tệp đúng source directory giúp plugin áp dụng đúng cách xử lý.

### Source set tùy chỉnh

Một dự án có thể có thêm mã nguồn cho integration test, công cụ nội bộ hoặc một biến thể ứng dụng. Khi đó, nhóm có thể định nghĩa source set riêng thay vì đặt mọi tệp vào `src/main/java`.

Ví dụ Groovy DSL:

```groovy
sourceSets {
    integrationTest {
        java.srcDir 'src/integrationTest/java'
        resources.srcDir 'src/integrationTest/resources'
        compileClasspath += sourceSets.main.output
        runtimeClasspath += output + compileClasspath
    }
}
```

Đoạn cấu hình khai báo một source set tên `integrationTest` với vùng mã nguồn và tài nguyên riêng. Các task biên dịch, xử lý tài nguyên và classpath tương ứng được tạo theo quy tắc của Java Plugin. Dự án thường cần cấu hình thêm dependency và task kiểm thử để thực thi source set này.

Khi nhận diện mã nguồn, hãy kiểm tra source set thực tế của dự án. Đừng giả định tất cả mã nguồn đều nằm trong hai thư mục mặc định nếu build đã mở rộng cấu trúc.

## 3. Tài nguyên là đầu vào song song với mã nguồn

Tài nguyên (resources) là các tệp mà ứng dụng cần sử dụng nhưng không được biên dịch như mã Java. Ví dụ:

- `application.yml`, `application.properties` và các tệp cấu hình mặc định được đóng gói cùng ứng dụng.
- Tệp `.sql` dùng để khởi tạo schema hoặc dữ liệu mẫu.
- Template HTML, email template và tệp nội dung.
- Ảnh, font, biểu tượng, tệp JSON hoặc XML.
- Tệp metadata và các tài nguyên khác mà ứng dụng đọc khi chạy.

Với Java Plugin, tài nguyên chính thường nằm trong `src/main/resources`, còn tài nguyên kiểm thử nằm trong `src/test/resources`.

```text
src/
├── main/
│   ├── java/
│   └── resources/
│       ├── application.yml
│       ├── schema.sql
│       └── templates/
│           └── welcome.html
└── test/
    ├── java/
    └── resources/
        └── fixtures/
            └── sample.json
```

Task `processResources` xử lý và sao chép tài nguyên của source set chính vào output tương ứng; `processTestResources` làm việc tương tự với tài nguyên kiểm thử. Khi đóng gói JAR, tài nguyên chính thường được đưa vào archive cùng class files.

Ví dụ, nếu `application.yml` thay đổi nhưng task tạo artifact không nhận diện được tệp đó là đầu vào, ứng dụng có thể tiếp tục được đóng gói với cấu hình cũ. Với source set chuẩn, Java Plugin đã thiết lập quan hệ cần thiết giữa resource processing và các task sử dụng output. Với custom task hoặc custom source set, người viết build cần đảm bảo khai báo đúng file collection và quan hệ đầu vào/đầu ra.

### Tài nguyên được lọc hoặc biến đổi

Một số dự án thay placeholder trong tài nguyên khi build, chẳng hạn đưa phiên bản ứng dụng vào tệp metadata. Khi đó, cả tệp gốc lẫn giá trị thay thế đều ảnh hưởng output.

Ví dụ:

```groovy
tasks.named('processResources') {
    filesMatching('build-info.properties') {
        expand(version: project.version)
    }
}
```

Trong ví dụ này, nội dung `build-info.properties` và giá trị `project.version` cùng ảnh hưởng tệp đã xử lý. Nếu dùng filtering, cần xác định những giá trị nào thực sự thay đổi output và đảm bảo chúng được cung cấp ổn định, minh bạch. Không đưa mật khẩu hoặc token vào tài nguyên được đóng gói.

## 4. Tệp cấu hình build quyết định cách Gradle làm việc

Tệp cấu hình build không nhất thiết được đưa vào JAR, nhưng có thể thay đổi task graph hoặc kết quả của các task. Đây là nhóm đầu vào cấu hình rất quan trọng.

### `settings.gradle` hoặc `settings.gradle.kts`

Settings file xác định cấu trúc build, tên root project, các project con và một số cấu hình ở cấp build như plugin management và repository cho plugin.

Ví dụ:

```groovy
rootProject.name = 'inventory-system'

include 'inventory-api'
include 'inventory-core'
```

Nếu thay đổi project được include hoặc cách tổ chức build, Gradle có thể cấu hình một tập project và quan hệ khác. Vì vậy, settings file là đầu vào cấu hình của toàn build.

### `build.gradle` hoặc `build.gradle.kts`

Build script khai báo plugin, dependency, repository, source set, task, compiler options và nhiều quy tắc khác.

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.2.0'

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Thay đổi plugin, phiên bản dependency, compiler options hoặc cấu hình test có thể làm thay đổi graph, classpath hay kết quả build. Các build script và script/plugin được áp dụng cần được quản lý như mã cấu hình có ảnh hưởng tới build.

### `gradle.properties`

Tệp này có thể chứa các thuộc tính Gradle hoặc thuộc tính dự án, ví dụ:

```properties
org.gradle.parallel=true
org.gradle.caching=true
org.gradle.jvmargs=-Xmx2g
appProfile=local
```

Thuộc tính có thể ảnh hưởng đến hiệu năng, cách cấu hình hoặc logic build nếu build script đọc chúng. Cần phân biệt thuộc tính điều khiển Gradle với project property mà build script sử dụng. Một giá trị chỉ ảnh hưởng đến kết quả task khi task hoặc cấu hình liên quan thực sự đọc giá trị đó.

Không nên đặt mật khẩu, access token hoặc secret trực tiếp trong `gradle.properties` được commit. Hãy dùng cơ chế quản lý secret phù hợp của máy phát triển hoặc CI.

### Version catalog và cấu hình dependency

Version catalog thường được lưu trong `gradle/libs.versions.toml`. Nó gom alias plugin và dependency để build script tham chiếu thống nhất.

```toml
[versions]
junit = "5.10.2"

[libraries]
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }
```

Khi thay đổi version catalog, dependency hoặc plugin được chọn có thể thay đổi. Các tệp dependency lock và dependency verification metadata (nếu dự án sử dụng) cũng là đầu vào quan trọng để xác định phiên bản đã khóa và kiểm chứng artifact được tải về.

## 5. Dependency và repository cũng ảnh hưởng build

Mã nguồn thường tham chiếu tới các lớp trong thư viện bên ngoài. Những thư viện đó được khai báo trong dependency configuration và được Gradle phân giải từ repository.

```groovy
repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
}
```

Dependency ảnh hưởng classpath của compiler, runtime và test. Thay đổi version có thể làm thay đổi API có sẵn, hành vi thư viện hoặc nội dung được đóng gói.

Khi kiểm tra dependency, cần xem:

- Tọa độ dependency như group, artifact và version.
- Configuration mà dependency được khai báo, ví dụ `implementation`, `runtimeOnly`, `testImplementation`.
- Repository dùng để phân giải dependency.
- Dependency transitives được kéo vào từ thư viện khác.
- Version catalog, dependency constraints, lockfiles và verification metadata nếu có.

Một khai báo version động như `1.+` hoặc `latest.release` có thể phân giải thành phiên bản khác ở những thời điểm khác nhau. Điều này làm build khó tái lập. Với build cần tính ổn định, nên dùng phiên bản xác định và cân nhắc dependency locking cùng dependency verification.

Repository URL và trạng thái dịch vụ bên ngoài có thể ảnh hưởng khả năng tải dependency. Tuy nhiên, một khi dependency đã được phân giải và cache, Gradle có thể không cần tải lại trong mỗi lần build. Cache tải dependency không thay thế việc khai báo phiên bản và xác minh nguồn gốc dependency.

## 6. Phiên bản công cụ và môi trường build

Ngay cả khi mã nguồn và cấu hình giống nhau, kết quả build vẫn có thể khác nếu sử dụng phiên bản công cụ khác nhau hoặc môi trường khác nhau.

Các thành phần thường cần nhận diện gồm:

- **Gradle Wrapper:** `gradlew`, `gradlew.bat` và `gradle/wrapper/gradle-wrapper.properties` xác định cách dự án chọn phiên bản Gradle.
- **JDK/Java toolchain:** phiên bản Java dùng để chạy Gradle và phiên bản compiler/runtime được chọn cho các task.
- **Plugin versions:** plugin Gradle có thể thay đổi cách cấu hình task, compiler, đóng gói hoặc kiểm tra.
- **Compiler options:** source/target compatibility, release level, encoding và các cờ compiler.
- **Hệ điều hành và công cụ ngoài:** có thể ảnh hưởng task gọi native executable, shell script, Docker hoặc công cụ xử lý tài nguyên.

Ví dụ cấu hình Java toolchain:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Toolchain giúp dự án khai báo rõ phiên bản Java cần dùng cho các task Java phù hợp. Nó không có nghĩa mọi tác vụ trong build đều chạy trong cùng một JVM hoặc hệ điều hành; các plugin và công cụ ngoài có thể có yêu cầu riêng.

Để build trên máy cá nhân và CI nhất quán hơn, hãy commit Gradle Wrapper, cố định phiên bản plugin/dependency phù hợp và khai báo toolchain. Đồng thời, tài liệu hóa những công cụ ngoài cần có trong môi trường build.

## 7. Biến môi trường và tham số dòng lệnh

Build script có thể đọc project property, system property hoặc environment variable. Ví dụ:

```groovy
def targetEnvironment = providers.gradleProperty('targetEnvironment')
    .orElse('local')

tasks.register('printTargetEnvironment') {
    inputs.property('targetEnvironment', targetEnvironment)
    doLast {
        println "Target environment: ${targetEnvironment.get()}"
    }
}
```

Có thể truyền giá trị khi chạy:

```bash
./gradlew printTargetEnvironment -PtargetEnvironment=staging
```

Nếu một property thay đổi nội dung output, task cần khai báo property đó là input. Nếu build script đọc một biến môi trường để chọn cấu hình, cần xác định rõ biến đó ảnh hưởng tới cấu hình build hay output task nào.

Ví dụ đọc biến môi trường:

```groovy
def deploymentRegion = providers.environmentVariable('DEPLOYMENT_REGION')
    .orElse('local')
```

Không nên đọc biến môi trường rải rác bên trong action rồi bỏ qua việc mô tả nó như một đầu vào. Khi dữ liệu ảnh hưởng output nhưng không được khai báo, Gradle có thể coi output cũ vẫn hợp lệ dù giá trị thực tế đã thay đổi.

Credentials là trường hợp cần xử lý riêng. Token và mật khẩu thường chỉ cấp quyền truy cập repository hoặc dịch vụ; không nên ghi chúng vào log, artifact, cache chia sẻ hoặc build file. Nếu một secret thực sự làm thay đổi nội dung output, hãy xem lại thiết kế để tránh output phụ thuộc vào secret. Với thao tác upload, thường cần credentials để xác thực nhưng giá trị bí mật không nên trở thành dữ liệu được công bố.

## 8. Phân biệt đầu vào cấu hình với đầu vào task

Để biết một thay đổi có thể làm build chạy lại hay không, cần xác định thay đổi đó tác động ở tầng nào.

| Dữ liệu | Vai trò thường gặp | Ví dụ |
|---|---|---|
| `settings.gradle` | Đầu vào cấu hình build | Include project, plugin management |
| `build.gradle` | Đầu vào cấu hình project và task | Plugin, dependency, task configuration |
| `gradle.properties` | Cấu hình Gradle/project | Project property, JVM args |
| `src/main/java/**/*.java` | Đầu vào task biên dịch | Lớp Java chính |
| `src/main/resources/**` | Đầu vào task xử lý tài nguyên | YAML, SQL, template |
| `src/test/java/**/*.java` | Đầu vào task biên dịch test | Unit test, integration test nếu thuộc source set |
| Dependency đã phân giải | Classpath/runtime input | JAR từ Maven repository |
| Java toolchain | Cấu hình công cụ thực thi task | JDK 21 |
| Project property được task sử dụng | Đầu vào giá trị của task | `-PtargetEnvironment=staging` |
| Environment variable được task sử dụng | Đầu vào môi trường | `DEPLOYMENT_REGION` |

Không phải mọi tệp cấu hình đều phải được thêm thủ công vào `inputs` của mọi task. Plugin Gradle chuẩn đã khai báo input/output cho các task mà plugin quản lý. Người viết custom task cần khai báo dữ liệu mà action của task thực sự đọc. Đối với build configuration, Gradle cũng có cơ chế theo dõi các tệp và script cấu hình để xác định khi nào cần cấu hình lại build.

Điểm cần tránh là nhầm lẫn giữa “tệp tồn tại trong repository” với “tệp là input của mọi task”. Ví dụ, README có thể nằm trong repository nhưng không ảnh hưởng `compileJava`. Nếu một task sinh tài liệu đọc README, lúc đó README là input của task sinh tài liệu đó.

## 9. Khai báo đầu vào cho custom task

Khi tự viết task, hãy mô tả rõ dữ liệu mà task đọc bằng các property phù hợp. Gradle dùng thông tin này để kiểm tra trạng thái task, incremental build và build cache khi các điều kiện khác cũng được đáp ứng.

Ví dụ task tạo danh sách tên tài nguyên từ một thư mục:

```groovy
abstract class ListResourcesTask extends DefaultTask {
    @InputDirectory
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract DirectoryProperty getResourceDirectory()

    @Input
    abstract Property<String> getApplicationName()

    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void generate() {
        def directory = resourceDirectory.get().asFile
        def output = outputFile.get().asFile
        output.parentFile.mkdirs()

        def names = []
        directory.eachFileRecurse { file ->
            if (file.isFile()) {
                names << directory.toPath()
                    .relativize(file.toPath())
                    .toString()
            }
        }
        names.sort()

        output.text = "${applicationName.get()}\n" + names.join('\n')
    }
}

tasks.register('listMainResources', ListResourcesTask) {
    resourceDirectory.set(layout.projectDirectory.dir('src/main/resources'))
    applicationName.set('inventory-service')
    outputFile.set(layout.buildDirectory.file('reports/main-resources.txt'))
}
```

Trong ví dụ:

- Thư mục tài nguyên là input dạng directory.
- `applicationName` là input dạng giá trị đơn.
- Tệp báo cáo là output của task.
- Nếu tên ứng dụng hoặc nội dung thư mục thay đổi, Gradle có thông tin để xác định task cần thực hiện lại.

Đây là ví dụ minh họa cho việc mô tả input/output; trong build thực tế, nên cân nhắc dùng API Gradle phù hợp để tránh đọc trạng thái project tùy tiện bên trong task action. Với task có thể cache, cần thiết kế action xác định, khai báo đủ input/output và tuân thủ yêu cầu về cacheability.

Các annotation thường gặp:

| Annotation / property | Công dụng |
|---|---|
| `@Input` | Giá trị đơn ảnh hưởng kết quả |
| `@InputFile` | Một tệp đầu vào |
| `@InputFiles` | Tập hợp tệp đầu vào |
| `@InputDirectory` | Thư mục đầu vào |
| `@Classpath` | Tập hợp tệp classpath, với cách chuẩn hóa phù hợp cho classpath |
| `@CompileClasspath` | Classpath đầu vào được chuẩn hóa cho mục đích biên dịch |
| `@Nested` | Nhóm property lồng nhau có input được mô tả |
| `@OutputFile` | Một tệp đầu ra |
| `@OutputDirectory` | Thư mục đầu ra |

Chọn annotation dựa trên bản chất dữ liệu. Không khai báo một thư mục output như input chỉ để buộc task chạy; hãy mô tả đúng luồng dữ liệu và quan hệ giữa task.

## 10. Đầu vào ẩn và hậu quả khi khai báo thiếu

**Đầu vào ẩn (implicit/undeclared input)** là dữ liệu task sử dụng nhưng Gradle không biết hoặc không theo dõi đúng cách. Ví dụ:

- Task đọc một tệp JSON bằng đường dẫn cố định trong action nhưng không khai báo nó là input.
- Task gọi `System.getenv('APP_VERSION')` để ghi phiên bản vào output nhưng không khai báo giá trị đó.
- Task chạy một công cụ ngoài có phiên bản thay đổi nhưng build không kiểm soát phiên bản công cụ.
- Task tải dữ liệu mới nhất từ URL không cố định mà không xác định checksum hoặc version.
- Task phụ thuộc vào thư mục hiện tại, đồng hồ hệ thống hoặc locale của máy mà không mô tả ảnh hưởng.

Khi đầu vào ẩn thay đổi, Gradle có thể không nhận ra output cần được tạo lại. Điều này gây ra các biểu hiện như:

- Build báo `UP-TO-DATE` dù kết quả đáng lẽ phải thay đổi.
- Máy cá nhân tạo artifact khác với CI dù cùng commit.
- Build cache trả về output không phù hợp với môi trường hoặc dữ liệu hiện tại.
- Một bước build chỉ chạy đúng khi người thực hiện nhớ thao tác thủ công trước đó.

Không phải mọi yếu tố môi trường đều cần đưa vào mọi task. Chỉ dữ liệu thực sự ảnh hưởng kết quả của task mới là input của task đó. Tuy nhiên, khi một giá trị ảnh hưởng output, cần khai báo hoặc kiểm soát nó bằng cơ chế thích hợp.

## 11. Xây dựng build có thể tái lập

Build có thể tái lập (reproducible build) hướng tới việc cùng một tập đầu vào được kiểm soát sẽ tạo ra kết quả tương đương, bất kể build chạy trên máy nào trong các môi trường được hỗ trợ.

Một số thực hành giúp đạt mục tiêu này:

1. Dùng Gradle Wrapper để thống nhất phiên bản Gradle.
2. Khai báo Java toolchain và phiên bản plugin rõ ràng.
3. Dùng dependency version xác định; cân nhắc dependency locking và verification.
4. Commit build scripts, version catalog và những metadata cấu hình cần thiết.
5. Đặt mã nguồn và tài nguyên đúng source set; tránh phụ thuộc vào tệp nằm ngoài repository mà không khai báo.
6. Khai báo input/output của custom task đầy đủ.
7. Tránh dùng dữ liệu thay đổi theo thời gian hoặc trạng thái máy cá nhân nếu không có chủ đích.
8. Kiểm soát encoding, locale, timezone và công cụ ngoài khi chúng có thể ảnh hưởng output.
9. Không ghi credentials vào mã nguồn, artifact hoặc log.
10. Kiểm tra output trên CI trong môi trường được định nghĩa rõ.

Reproducibility không chỉ là chạy lại cùng một lệnh. Nó đòi hỏi nhận diện và kiểm soát tập dữ liệu ảnh hưởng kết quả. Nếu một dependency hoặc công cụ ngoài được cập nhật ngầm, hai lần build có thể khác nhau dù mã nguồn không thay đổi.

## 12. Cách lần theo đầu vào khi kết quả build bất ngờ

Khi artifact không phản ánh thay đổi mới nhất hoặc build trên CI khác máy cá nhân, hãy lần theo dữ liệu theo thứ tự:

1. Xác định task tạo output sai, ví dụ `compileJava`, `processResources`, custom code generation hoặc `jar`.
2. Liệt kê các tệp, giá trị và dependency mà task đó đọc.
3. Kiểm tra dữ liệu nào thay đổi kể từ lần build trước.
4. Xác nhận task/plugin đã khai báo những dữ liệu đó là input đúng cách.
5. Kiểm tra build script, source set, toolchain, dependency resolution và biến môi trường liên quan.
6. Dùng `--info` hoặc `--scan` nếu tổ chức cho phép để hiểu lý do task chạy, bị bỏ qua hoặc được lấy từ cache.
7. Chạy lại task trong điều kiện được kiểm soát và kiểm tra output được tạo.

Một số tình huống điển hình:

| Tình huống | Đầu vào nên kiểm tra |
|---|---|
| Sửa Java nhưng class file không đổi | Source directory, source set, task compile và trạng thái incremental |
| Sửa `application.yml` nhưng JAR vẫn chứa cấu hình cũ | `src/main/resources`, `processResources`, resource filtering và task đóng gói |
| Đổi dependency nhưng kết quả không như mong đợi | Dependency configuration, version catalog, lockfile, repository và resolved classpath |
| CI dùng JDK khác máy local | Gradle Wrapper, Java toolchain và môi trường CI |
| Đổi `-PtargetEnvironment` nhưng báo cáo không đổi | Property có được đọc và khai báo là input của task tạo báo cáo hay không |
| Task luôn `UP-TO-DATE` dù tệp cấu hình thay đổi | Tệp cấu hình có được khai báo là input của custom task hay không |

Lệnh `./gradlew tasks --all` giúp nhận diện task; `./gradlew <task> --info` cung cấp thêm thông tin thực thi; `--dry-run` cho thấy task graph mà không chạy action. Những lệnh này hỗ trợ chẩn đoán, nhưng vẫn cần đọc cấu hình và kiểm tra output để xác định đầu vào bị thiếu.

## 13. Quy trình nhận diện đầu vào cho một dự án Java

Khi tiếp nhận một dự án hoặc thiết kế build mới, có thể lập bản đồ đầu vào theo các bước sau:

1. **Khảo sát cấu trúc thư mục:** tìm `src/main/java`, `src/main/resources`, `src/test/java`, `src/test/resources` và các source set tùy chỉnh.
2. **Đọc settings và build scripts:** xác định project, plugin, task, dependency, repository và compiler options.
3. **Đọc cấu hình Gradle:** kiểm tra Wrapper, `gradle.properties`, version catalog, lockfiles và verification metadata.
4. **Xác định công cụ:** phiên bản Gradle, JDK/toolchain và các công cụ ngoài được gọi trong build.
5. **Tìm dữ liệu môi trường:** project property, system property và environment variable được dùng trong cấu hình hoặc task action.
6. **Theo từng task:** xác định task đọc dữ liệu nào, tạo output nào và task sau sử dụng output đó ra sao.
7. **Kiểm tra đầu vào ẩn:** tìm đường dẫn cố định, file đọc trực tiếp, network request, thời gian hệ thống và trạng thái máy không được khai báo.
8. **Ghi lại nguồn và cách kiểm soát:** nêu vị trí dữ liệu, chủ sở hữu, phiên bản hoặc checksum nếu cần, và cách cung cấp nhất quán cho local/CI.

Một bảng kiểm kê đầu vào đơn giản có thể trông như sau:

| Nhóm | Ví dụ | Nơi khai báo/kiểm soát | Task hoặc giai đoạn bị ảnh hưởng |
|---|---|---|---|
| Mã nguồn chính | `src/main/java` | Source set `main` | `compileJava` |
| Tài nguyên chính | `src/main/resources` | Source set `main` | `processResources`, `jar` |
| Mã kiểm thử | `src/test/java` | Source set `test` | `compileTestJava`, `test` |
| Tài nguyên test | `src/test/resources` | Source set `test` | `processTestResources`, `test` |
| Dependency | Maven coordinates | `dependencies`, repository, lockfile | Compile, test, runtime, package |
| Cấu hình build | Settings, build scripts, properties | Gradle configuration | Build configuration và nhiều task |
| Toolchain | JDK/Gradle/plugin versions | Wrapper, plugin DSL, Java toolchain | Compile, test, plugin tasks |
| Môi trường | Project properties, environment | CI variables hoặc local config | Những task thực sự đọc giá trị |

## 14. Nguyên tắc cần ghi nhớ

Mã nguồn, tài nguyên và cấu hình đều có thể là đầu vào build, nhưng chúng đi vào build ở những tầng khác nhau. Mã Java thường được compiler xử lý; tài nguyên thường được sao chép hoặc lọc; build scripts và settings quyết định cách Gradle cấu hình project và task; dependency cung cấp classpath; toolchain và môi trường xác định công cụ cùng điều kiện thực thi.

Khi một task tự đọc thêm dữ liệu, dữ liệu đó cần được mô tả như input phù hợp. Khi một task tạo ra dữ liệu cho task khác, hãy nối output và input qua cơ chế của Gradle để quan hệ được thể hiện rõ. Việc nhận diện đúng đầu vào giúp Gradle biết khi nào cần thực hiện lại công việc, hỗ trợ incremental build và build cache, đồng thời làm cho kết quả giữa máy phát triển và CI nhất quán hơn.

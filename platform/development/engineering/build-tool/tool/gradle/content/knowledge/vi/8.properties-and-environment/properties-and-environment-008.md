# Tách cấu hình môi trường và tránh phụ thuộc ngầm vào máy cá nhân trong Gradle

## 1. Vấn đề: build chạy trên máy tôi nhưng lỗi trên máy khác

Một Gradle build đáng tin cậy phải mô tả rõ **nó cần những đầu vào nào**, **đọc chúng từ đâu** và **khi thiếu thì xử lý ra sao**. Lỗi “works on my machine” thường xuất phát từ điều ngược lại: mã build vô tình dựa vào JDK mặc định, biến môi trường, đường dẫn ổ cứng, repository, cache, credentials hoặc file chỉ tồn tại trên máy của tác giả.

Ví dụ về phụ thuộc ngầm:

```groovy
// build.gradle — ví dụ sai, chỉ để nhận diện anti-pattern
def localSdk = '/Users/alice/tools/custom-sdk'
def target = System.getenv('TARGET_ENV') ?: 'production'
def buildId = new Date().time

tasks.register('showConfig') {
    doLast {
        println "SDK: $localSdk; target=$target; buildId=$buildId"
    }
}
```

Đoạn script có ba vấn đề khác nhau:

1. `/Users/alice/...` là đường dẫn tuyệt đối đặc thù macOS và tài khoản của một người. Windows/Linux/CI có thể không có nó.
2. Biến `TARGET_ENV` không được khai báo trong hợp đồng build; khi thiếu lại rơi về `production`, khiến một thao tác local có thể dùng sai môi trường.
3. `new Date().time` được tính lúc configuration, làm giá trị thay đổi theo thời điểm, khó tái lập và không đại diện cho input ổn định.

**Cách sửa là thiết kế ranh giới cấu hình**: giá trị ổn định thuộc repository; lựa chọn theo lần chạy được truyền rõ qua Gradle property; thông tin hạ tầng/secret được cấp qua môi trường an toàn; đường dẫn trỏ vào project hoặc được khai báo làm input; Java/Gradle version được chỉ định và kiểm tra. Một biến môi trường không tự động “xấu”, nhưng **đọc ngầm, dùng mặc định nguy hiểm hoặc bỏ qua việc khai báo input** mới là vấn đề.

## 2. Phân loại cấu hình trước khi chọn nơi lưu

| Loại thông tin | Ví dụ | Nguồn phù hợp | Commit vào Git? |
| --- | --- | --- | --- |
| **Quy ước dùng chung** | Phiên bản Gradle Wrapper, Java toolchain, nhóm task, tên artifact, build flags được thống nhất | `gradle/wrapper/gradle-wrapper.properties`, `build.gradle(.kts)`, `settings.gradle(.kts)`, root `gradle.properties` | Thường **có**, sau review |
| **Lựa chọn cho một lần chạy** | `buildTarget=dev`, cờ bật test e2e, tag release, feature flag build | `-P...` / `--project-prop ...`, hoặc project property được CI cung cấp | Không cần commit từng giá trị |
| **Cấu hình riêng từng máy** | Đường dẫn JDK cụ thể, proxy, tài khoản repository, dung lượng daemon theo thiết bị | `GRADLE_USER_HOME/gradle.properties`, biến môi trường, IDE/CI config | **Không** commit đường dẫn/tài khoản cá nhân |
| **Secret** | Registry token, signing key password, repo credentials | Secret store của CI, Gradle credentials API, user-home properties được bảo vệ hoặc biến môi trường | **Không** commit secret |
| **Đầu vào thực sự của task** | File schema, environment tag, source files, toolchain | `@Input`, `@InputFile`, `@InputFiles`, `@OutputFile`, Gradle `Provider` | Commit **khai báo input**, không nhất thiết commit giá trị môi trường |
| **Dữ liệu được sinh** | Jar, report, manifest, generated sources | `layout.buildDirectory` / output properties | Không commit chỉ để build chạy |
| **Phụ thuộc ngoài** | Maven dependencies, Gradle plugins, private repo URL | Repository config + versions/locks/verification theo chính sách | Có thể commit tọa độ/lock; giữ credentials ngoài Git |

Hai quyết định cần tách biệt:

- **Giá trị có thể thay đổi giữa môi trường** không đồng nghĩa nó là secret. Ví dụ `buildTarget` có thể đưa vào command line và log; token phải được bảo vệ.
- **Nguồn cấu hình** khác với **input của task**. Có thể đọc `BUILD_ID` từ môi trường, nhưng muốn Gradle nhận ra giá trị thay đổi và task cần chạy lại thì phải nối nó vào một property/input của task.

Một dự án tốt có một **hợp đồng build** ngắn: đầu vào bắt buộc, đầu vào có default, cách cấu hình ở local/CI, cách kiểm chứng. Nhờ đó người mới không phải sao chép bí mật từ máy đồng nghiệp hay sửa build script để chạy được.

## 3. Năm cơ chế hay gặp và vai trò của chúng

| Cơ chế | Cú pháp ví dụ | Dùng cho điều gì |
| --- | --- | --- |
| Gradle project property | `-PbuildTarget=ci` | Chỉ rõ lựa chọn thuộc **build**, có thể đọc bằng `providers.gradleProperty("buildTarget")` |
| Project property qua JVM system property | `-Dorg.gradle.project.buildTarget=ci` | Cách khác cấp đúng project property |
| `gradle.properties` | `buildTarget=local` hoặc `org.gradle.caching=true` | Lưu project property hoặc Gradle property; có thể nằm ở root, user home hoặc Gradle installation |
| Biến môi trường | `BUILD_ID=123`, `JAVA_HOME`, `ORG_GRADLE_PROJECT_buildTarget` | Cung cấp dữ liệu từ shell, IDE hoặc CI |
| Java system property | `-Dexample.mode=debug` | Cấu hình Java process chạy Gradle; trong script đọc bằng `providers.systemProperty("example.mode")` |

Phân biệt hai cặp rất dễ nhầm:

- `-PbuildTarget=ci` tạo **project property** tên `buildTarget`; `-DbuildTarget=ci` tạo **system property** tên `buildTarget`. Chúng **không hoán đổi** với nhau. Muốn tạo project property từ `-D`, cần prefix `org.gradle.project.`.
- `org.gradle.caching=true` là **Gradle property điều khiển công cụ**; `buildTarget=local` là **project property điều khiển logic dự án**. Không dùng key `org.gradle.*` tùy ý cho cấu hình nghiệp vụ.

### 3.1. Thứ tự ưu tiên của project properties

Khi nhiều nguồn cùng đặt project property tên `buildTarget`, thứ tự thường là **ưu tiên cao đến thấp**:

1. Lệnh `-PbuildTarget=...`.
2. System property có tên `org.gradle.project.buildTarget` (ví dụ `-Dorg.gradle.project.buildTarget=...`).
3. Key `buildTarget=...` trong `gradle.properties`.
4. Biến môi trường `ORG_GRADLE_PROJECT_buildTarget=...`.

Trong nhóm file `gradle.properties`, Gradle ưu tiên **`GRADLE_USER_HOME/gradle.properties` trước file ở root project, rồi file tại installation `GRADLE_HOME`**. Vì vậy một giá trị đặt ở root có thể bị cấu hình user-home của developer ghi đè. Đừng gọi root `gradle.properties` là “giá trị không thể thay đổi”; muốn CI deterministic, hãy dùng input được cấp có chủ đích và kiểm tra khi chạy.

Lưu ý: bảng trên nói về cách **nạp project property theo Gradle**, không phải thứ tự ưu tiên của một biểu thức do bạn tự viết như `providers.environmentVariable("A").orElse(providers.gradleProperty("B"))`. Chính thứ tự trong `orElse` quyết định giá trị của biểu thức đó.

### 3.2. `gradle.properties` không giống `local.properties`

Gradle **tự đọc** những file `gradle.properties` tại các vị trí được hỗ trợ. Trong Gradle core, file tên `local.properties` **không tự trở thành project properties** chỉ vì bạn tạo nó; một plugin (ví dụ Android) hoặc code build phải định nghĩa việc đọc nó. Nếu muốn hỗ trợ file local tùy chọn, cần thiết kế và tài liệu hóa rõ file path, schema, default, validation, việc ignore trong Git và cách khai báo file làm input. Không coi một file vô hình trên máy tác giả là hợp đồng chung của mọi người.

## 4. Thiết kế cấu hình repository, người dùng và CI

Ví dụ một Gradle project chọn Java 17 và có task sinh manifest từ hai giá trị vô hại:

```text
portable-build/
├── settings.gradle
├── build.gradle
├── gradle.properties
├── gradlew
├── gradlew.bat
└── gradle/
    └── wrapper/
        ├── gradle-wrapper.jar
        └── gradle-wrapper.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'portable-build'
```

Root `gradle.properties` — **chỉ các lựa chọn dùng chung, không chứa đường dẫn hay mật khẩu**:

```properties
org.gradle.caching=true
```

Thư mục `gradle/wrapper` và hai script Wrapper được tạo/commit theo quy trình Gradle Wrapper của repository. Nếu repo đã có Wrapper thì không tạo lại. Bản phân phối Gradle cần tương thích với JDK đang dùng; cấu hình `toolchain` phần sau chỉ định JDK cho code Java chứ không tự khắc phục một Gradle runtime quá cũ.

**Không đưa các dòng dưới đây vào root `gradle.properties` nếu chúng thuộc một máy:**

```properties
# Ví dụ không nên commit:
# org.gradle.java.home=C:/Users/alice/.jdks/temurin-17
# systemProp.http.proxyHost=proxy-internal-only
# repositoryPassword=my-real-token
```

Giá trị tương ứng, nếu cần, thuộc `GRADLE_USER_HOME/gradle.properties` trên máy đã cấu hình, biến môi trường hoặc secret store của CI. Tài liệu onboarding cần ghi **tên key và mục đích**, không ghi giá trị bí mật.

## 5. Ví dụ chạy được: Gradle Providers và khai báo task inputs/outputs

Mục tiêu: sinh file `build/generated/environment.txt` với `target` lấy từ project property có default `local`, và `buildId` lấy từ biến môi trường `BUILD_ID` có default `none`. File được tạo tại **build directory của project**, không đặt ở đường dẫn máy cá nhân.

Dán nguyên nội dung sau vào **`build.gradle` (Groovy DSL)** của ví dụ `portable-build`:

```groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction

abstract class WriteEnvironmentManifest extends DefaultTask {
    @Input
    abstract Property<String> getBuildTarget()

    @Input
    abstract Property<String> getBuildId()

    @OutputFile
    abstract RegularFileProperty getDestination()

    @TaskAction
    void writeManifest() {
        File output = destination.get().asFile
        output.parentFile.mkdirs()
        output.setText(
            "target=${buildTarget.get()}\nbuildId=${buildId.get()}\n",
            'UTF-8'
        )
    }
}

tasks.register('writeEnvironmentManifest', WriteEnvironmentManifest) {
    buildTarget.set(
        providers.gradleProperty('buildTarget').orElse('local')
    )
    buildId.set(
        providers.environmentVariable('BUILD_ID').orElse('none')
    )
    destination.set(
        layout.buildDirectory.file('generated/environment.txt')
    )
}
```

**Phân tích từng phần:**

- `WriteEnvironmentManifest` là task type riêng. `@Input` khai báo hai String có ảnh hưởng đến nội dung output. `@OutputFile` khai báo file tạo ra.
- `providers.gradleProperty('buildTarget')` tìm giá trị qua cơ chế project property (bao gồm `-P`, `gradle.properties`, v.v.). `orElse('local')` là default rõ ràng của **bài demo**, không phải luật áp dụng cho deployment production.
- `providers.environmentVariable('BUILD_ID')` chỉ đọc đúng một biến được chỉ định; không quét tất cả môi trường. `orElse('none')` tránh yêu cầu máy cá nhân phải có `BUILD_ID`.
- `destination.set(layout.buildDirectory.file(...))` để Gradle quản lý output theo build directory, phù hợp các OS và cấu hình `layout.buildDirectory` nếu project thay đổi.
- Trong `@TaskAction`, task chỉ dùng các property của **chính nó**; không đọc `project`, `System.getenv` hoặc trạng thái từ cấu hình bên ngoài vào lúc chạy.
- Nội dung output được xác định bởi inputs, nên Gradle có thể kiểm tra up-to-date/build cache theo metadata thích hợp. `@OutputFile` không tự đảm bảo toàn bộ task an toàn để lưu cache nếu task còn side effect hay input khác chưa khai báo; ví dụ này cố tình chỉ ghi một file đơn giản.

### 5.1. Chạy ở Linux/macOS với giá trị mặc định

```bash
./gradlew -q writeEnvironmentManifest
cat build/generated/environment.txt
```

Giả sử **chưa đặt `buildTarget` trong user-home properties hay biến override, và `BUILD_ID` không tồn tại**, nội dung file là **chính xác**:

```text
target=local
buildId=none
```

Task không tự in hai dòng trên ra stdout: lệnh `cat` mới đọc file. Nếu task đã up-to-date, Gradle có thể bỏ qua task action, nhưng file vẫn có nội dung từ lần chạy hợp lệ trước.

### 5.2. Chạy với giá trị tường minh ở Linux/macOS

```bash
BUILD_ID=ci-42 ./gradlew -q writeEnvironmentManifest -PbuildTarget=ci
cat build/generated/environment.txt
```

Với cùng build demo, file được tạo/được cập nhật thành:

```text
target=ci
buildId=ci-42
```

Bởi vì hai input được khai báo, thay `-PbuildTarget` hoặc `BUILD_ID` khiến task cần xem xét thực thi lại; không phải sửa file `build.gradle` để chuyển môi trường.

### 5.3. Chạy trên Windows PowerShell

```powershell
$env:BUILD_ID = "ci-42"
.\gradlew.bat -q writeEnvironmentManifest -PbuildTarget=ci
Get-Content build\generated\environment.txt
```

Output file vẫn dùng cùng định dạng và cùng giá trị `target=ci`, `buildId=ci-42`. Trong Command Prompt có thể dùng `set BUILD_ID=ci-42` rồi `gradlew.bat ...`. Đừng dùng cú pháp `BUILD_ID=... command` của Bash trực tiếp trong PowerShell.

Ví dụ này **không chứa credentials**. Nếu `BUILD_ID` là dữ liệu nhạy cảm trong dự án thật, không ghi ra file/log; thiết kế riêng đường nhận secrets.

### 5.4. Khi nào phải yêu cầu cấu hình bắt buộc?

Default `local` phù hợp cho bài demo hoặc task kiểm thử local. Với task **deploy production, ký release, gửi artifact**, một default như `production` khi không có property là rủi ro.

Ví dụ kiểm tra đầu vào bắt buộc bằng `Provider`:

```groovy
tasks.register('validateDeploymentTarget') {
    def target = providers.gradleProperty('deploymentTarget')
    doLast {
        if (!target.present) {
            throw new GradleException(
                'Thiếu -PdeploymentTarget; chọn dev, staging hoặc production'
            )
        }
        def selected = target.get()
        if (!(selected in ['dev', 'staging', 'production'])) {
            throw new GradleException(
                "deploymentTarget không hợp lệ: ${selected}"
            )
        }
        println "Selected deployment target: ${selected}"
    }
}
```

Đây là **đoạn Groovy DSL thêm vào file demo**, task chỉ validate và in tên môi trường, **không deploy**. Nếu viết plugin/task sản xuất, hãy đưa validation vào task type/Provider theo contract, kết nối `dependsOn` đúng task cần xác thực và không capture đối tượng Project trong task action. Tên `production` chỉ được chấp nhận khi người gọi **chọn tường minh**; cùng một input không được tự hiểu khác giữa laptop và CI.

## 6. Hạn chế phụ thuộc vào biến môi trường không được tài liệu hóa

Biến môi trường là công cụ phổ biến trên CI, nhưng việc dựa vào trạng thái tùy ý của shell sẽ làm build khó hiểu.

**Cách dễ gây lệch:**

```groovy
// Anti-pattern: CI khác local chỉ vì tên biến ngầm trên máy.
if (System.getenv('CI')) {
    tasks.named('test') {
        enabled = false
    }
}
```

Có nhiều lỗi thiết kế: `test` có thể chưa tồn tại nếu chưa apply Java plugin; biến `CI` có thể có giá trị chuỗi `"false"` nhưng điều kiện vẫn truthy trong Groovy; việc tắt kiểm thử ngầm khiến CI và developer chạy bộ kiểm thử khác nhau. Gradle có thể theo dõi đọc biến môi trường trong configuration, nhưng điều đó **không thay thế một hợp đồng hành vi rõ ràng**.

**Thay bằng lựa chọn do người chạy quyết định**, ví dụ task tùy chọn tách riêng hoặc project property được đặt tên rõ:

```bash
./gradlew test
./gradlew test -PtestProfile=full
```

Nếu thực sự cần `testProfile` ảnh hưởng đến task, cấu hình plugin phải xác định các giá trị được chấp nhận và wiring vào task input/filter. Không tạo luật “có biến CI thì bỏ hết test”. Trong CI, khai báo biến/cờ ở workflow để người đọc thấy được điều kiện kiểm thử.

Một số biến có ý nghĩa kỹ thuật:

- `JAVA_HOME`: vị trí JDK cho công cụ/launcher theo cơ chế của Gradle và shell.
- `GRADLE_USER_HOME`: nơi lưu user-level config, daemon/cache, bản phân phối Wrapper.
- `ORG_GRADLE_PROJECT_key`: đưa `key` thành Gradle project property.
- `HTTP_PROXY`/`HTTPS_PROXY`: nhiều công cụ đọc chúng, nhưng **không nên giả định Gradle/JVM repository client tự nhận tất cả định dạng proxy theo cùng cách**; cấu hình theo JVM/Gradle/network thực tế.
- `BUILD_ID`, `DEPLOY_ENV`: không phải biến có ngữ nghĩa mặc định của mọi Gradle build. Chỉ có tác dụng nếu chính build hoặc plugin được viết để sử dụng.

Khi dùng `providers.environmentVariable("MY_KEY")`, chỉ định **một key cụ thể**; tránh quét `System.getenv()` để tìm những key có prefix nào đó nếu không cần, vì điều đó có thể đưa cả môi trường thành configuration input và khiến cache mất hiệu quả.

## 7. Không commit đường dẫn và trạng thái ổ cứng của developer

### 7.1. Dùng Gradle layout APIs thay vì path tuyệt đối

| Nhu cầu | Cách nên dùng | Cách dễ gây lỗi |
| --- | --- | --- |
| File cấu hình nguồn | `layout.projectDirectory.file("config/schema.json")` | `/Users/alice/code/schema.json` |
| Đường dẫn output | `layout.buildDirectory.file("generated/info.txt")` | `C:\Users\Alice\Desktop\out.txt` |
| Thư mục output | `layout.buildDirectory.dir("reports/custom")` | `/tmp/my-report` khi muốn dữ liệu được quản lý lâu dài |
| Đường dẫn thư mục hiện tại | `layout.projectDirectory` hoặc `rootProject.layout.projectDirectory` đúng ngữ cảnh | `new File(".")` với giả định mọi lệnh được gọi từ cùng current directory |
| Compiler JDK | `java.toolchain.languageVersion` | Hardcode `/opt/jdk-17/bin/javac` |
| File input của task | `RegularFileProperty` / `ConfigurableFileCollection` + annotation phù hợp | Task tự mò trong `~/Downloads` |

Các path dùng dấu `/` trong Gradle DSL thường được chuyển thành biểu diễn filesystem của OS. Dùng provider/file property giúp Gradle biết file thuộc input hay output và có cơ chế tính toán trễ; **chỉ thay một chuỗi path tuyệt đối thành path tương đối** chưa đủ nếu task vẫn đọc file ngoài khai báo.

Ví dụ input file do repository quản lý:

```groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

abstract class ShowSchemaName extends DefaultTask {
    @InputFile
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract RegularFileProperty getSchemaFile()

    @TaskAction
    void showName() {
        println "Schema file: ${schemaFile.get().asFile.name}"
    }
}

tasks.register('showSchemaName', ShowSchemaName) {
    schemaFile.set(layout.projectDirectory.file('config/schema.json'))
}
```

Đây là **đoạn minh họa**, muốn chạy phải có `config/schema.json` ở project root. `@InputFile` khai báo dependency vào nội dung file; `@PathSensitive(PathSensitivity.RELATIVE)` giúp kiểm tra đường dẫn theo vị trí tương đối thay vì mang absolute path của laptop vào fingerprint. Nó không có nghĩa Gradle sẽ tự tạo file còn thiếu.

### 7.2. Không lạm dụng `user.home`, `GRADLE_USER_HOME` hoặc thư mục tạm

`System.getProperty("user.home")` và `GRADLE_USER_HOME` có chỗ dùng chính đáng, nhưng chúng **khác nhau giữa người dùng/runner**, có thể chứa proxy credentials, caches, init scripts và `gradle.properties` riêng. Không trộn các đường dẫn này vào metadata build cần tái lập.

Nếu task thật cần thư mục cache, dùng API/service phù hợp và khai báo hành vi; nếu cần output được đưa vào artifact, đặt dưới `layout.buildDirectory`. Đừng chọn `~/Desktop` hoặc `Downloads` làm đầu ra mặc định của quy trình CI.

### 7.3. File `local.properties` nếu thực sự cần

Một ứng dụng có thể có cấu hình cá nhân `local.properties`, nhưng phải xây dựng **hợp đồng riêng**:

1. `local.properties.example` chứa key mẫu an toàn, không chứa secrets.
2. `local.properties` được ignore trong Git.
3. Build đọc file bằng API phù hợp, xử lý file không tồn tại và validate type/range.
4. Input file/config được khai báo để configuration cache và task up-to-date nhận ra thay đổi.
5. CI có đường cung cấp key tương đương mà không phải tạo file thủ công bằng thao tác ngoài tài liệu.

Với một hoặc hai giá trị, `-P...` và Gradle Providers thường **đơn giản hơn** tự phát minh một parser file cá nhân. Không ép mọi module có `local.properties` khi chỉ muốn đổi target hoặc version.

## 8. Cố định Gradle và Java, tránh “máy nào có JDK đó”

Hai JVM liên quan đến build Java có thể khác nhau:

1. **JVM chạy Gradle/Gradle Daemon**: quyết định Gradle core/plugins có chạy được hay không.
2. **JDK toolchain cho task Java**: có thể dùng để compile, test hoặc javadoc tùy cấu hình, giúp các máy dùng cùng yêu cầu ngôn ngữ/công cụ.

### 8.1. Gradle Wrapper

Repository cần commit `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar` và `gradle/wrapper/gradle-wrapper.properties`. Tất cả developer và CI gọi **Wrapper**:

```bash
./gradlew --version
./gradlew build
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat build
```

Đừng phụ thuộc vào một bản `gradle` toàn cục do máy cá nhân đã cài. Wrapper pin **Gradle version**, không tự pin JDK hoặc mọi dependency.

### 8.2. Java toolchain

Trong một project áp dụng Java plugin, file `build.gradle` có thể khai báo:

```groovy
import org.gradle.jvm.toolchain.JavaLanguageVersion

plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Đây là **một file ví dụ riêng** cho Java project; không dán nguyên lên phần demo `WriteEnvironmentManifest` nếu bạn muốn giữ demo chỉ có task sinh file. Toolchain cho Gradle biết cần JDK phù hợp để chạy các Java tasks. Nó **không tự cài được JDK trong mọi môi trường**: nếu máy thiếu JDK, cần cấu hình toolchain resolver/download repository được hỗ trợ hoặc cài JDK tương ứng trên runner. Toolchain và JVM chạy Gradle có các quy tắc khác nhau; kiểm tra version compatibility của Gradle Wrapper.

Khi có yêu cầu bytecode chạy được trên Java 17, đối với `JavaCompile` có thể kết hợp `options.release = 17` nếu phù hợp project và toolchain; đây là kiểm soát API/bytecode mục tiêu, không thay bằng `JAVA_HOME` tùy tiện.

### 8.3. Không commit `org.gradle.java.home` trỏ máy cá nhân

`org.gradle.java.home` có thể dùng để chỉ JDK cho Gradle process. Nhưng commit `org.gradle.java.home=C:/Users/alice/...` vào root `gradle.properties` sẽ làm build của Linux/macOS lỗi hoặc chọn sai JVM. Cấu hình đường dẫn riêng thuộc local user home hoặc CI environment. Nếu nhiều developer cần setup, tài liệu onboarding phải ghi yêu cầu **JDK version**, không ghi ổ đĩa cụ thể của một thành viên.

## 9. Repository, dependency và network cũng là một phần môi trường

Một build có thể chạy trên laptop vì cache đã đầy đủ hoặc Maven mirror chỉ cấu hình ở máy tác giả. CI mới clone có cache rỗng sẽ lỗi, dù Gradle script không dùng đường dẫn tuyệt đối.

**Hợp đồng dependency nên thể hiện:**

- Plugin repositories trong `pluginManagement.repositories` tại settings.
- Project dependency repositories trong `repositories` hoặc `dependencyResolutionManagement.repositories` theo policy.
- Artifact coordinates và versions đủ rõ; cân nhắc version catalogs, dependency locking và dependency verification khi cần tái lập chặt chẽ.
- Private repository URL/host được khai báo đúng cách, nhưng credentials được cấp qua môi trường an toàn.
- CI có quyền ra mạng hoặc dùng mirror/cache được cấp phát theo chính sách.

Ví dụ settings xác định nơi resolve plugin và project dependencies:

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'portable-build'
```

Đây là **một biến thể thay thế của `settings.gradle` demo**, không phải file cần đặt cạnh file settings cũ. Với doanh nghiệp, cần thêm repository nội bộ/credentials theo policy. `gradlePluginPortal()` giải quyết plugin, còn `mavenCentral()` trong `dependencyResolutionManagement` giải quyết dependency project; đừng nhầm `buildscript.repositories`, plugin repositories và project repositories.

**Tránh các giả định ngầm** như “máy tôi đã có dependency trong `~/.gradle/caches` nên CI sẽ build offline”. Lần chạy đầu trên máy sạch có thể cần download Gradle distribution, plugins và Maven dependencies. Cache là **tối ưu**, không phải nguồn duy nhất của artifact.

## 10. Secrets: tách nguồn cấp phát khỏi build logic

Mật khẩu/token là cấu hình theo môi trường nhưng có ràng buộc bảo mật riêng:

- Không commit `repositoryPassword`, API key, SSH private key, keystore password vào root `gradle.properties`, build scripts hoặc file mẫu.
- Không truyền secret bằng `-Ppassword=...` nếu lệnh có thể hiện trong shell history, process list hoặc CI logs. Cách này dễ làm lộ giá trị, dù Gradle vẫn nhận được project property.
- Ưu tiên secret store của CI, môi trường được kiểm soát hoặc `GRADLE_USER_HOME/gradle.properties` với quyền file phù hợp; thiết kế credentials bằng Gradle Credentials API khi repo/plugin hỗ trợ.
- Không in toàn bộ `./gradlew properties` vào log công khai; task này có thể hiển thị project properties chứa dữ liệu nhạy cảm.
- Không đưa secret vào `@Input` chỉ để “theo dõi thay đổi” mà không xét bảo vệ build cache/report; không in nó vào output artifact, `println`, test report hoặc build scan.

Một cú pháp cấp project property bằng environment từ CI:

```bash
export ORG_GRADLE_PROJECT_repoUser="user-from-ci"
# repoPassword do secret store cấp dưới dạng ORG_GRADLE_PROJECT_repoPassword.
./gradlew help
```

Đây chỉ là ví dụ **cách cấp**; bản thân `repoUser`/`repoPassword` không có tác dụng nếu build chưa dùng chúng trong credentials configuration. Không tự viết token thật vào script hoặc môi trường ví dụ. Với Gradle configuration cache, hạn chế đọc secrets eagerly tại configuration và giữ đúng policy lưu trữ cache/credentials của CI.

## 11. Configuration cache và build cache: không chữa được cấu hình ẩn

**Configuration cache** ghi nhớ kết quả configuration/task graph. **Build cache** tái sử dụng outputs của task khi fingerprint inputs/implementation phù hợp. Cả hai đều giúp build nhanh hơn, nhưng **không thể đoán input mà task không khai báo**.

Ví dụ hai cách đọc biến môi trường:

```groovy
// Eager: đọc ngay ở configuration (Gradle có thể track làm configuration input).
def idAtConfiguration = System.getenv('BUILD_ID') ?: 'none'

// Lazy: Provider chỉ đọc khi cần, có thể wire vào input của task.
def idProvider = providers.environmentVariable('BUILD_ID').orElse('none')
```

Gradle hiện đại có thể track các lần đọc `System.getenv("BUILD_ID")`/file ở configuration, làm cache entry bị invalidated khi giá trị đổi. Tuy nhiên, nếu task không khai báo input và chỉ dựa vào state mutable, task up-to-date/build cache vẫn có thể đưa kết quả sai. **Provider được nối vào `@Input`** như ví dụ `WriteEnvironmentManifest` giúp Gradle hiểu input ở cấp task.

Một số cách can thiệp không nên dùng trong configuration:

- Quét `System.getenv()` mọi key, rồi lựa chọn ngầm theo host/username.
- Chạy `git rev-parse`, gọi `ProcessBuilder` hoặc `execute()` trực tiếp trong configuration.
- Đọc file ngoài repository nhưng không mô tả nguồn, đường dẫn, khả năng không tồn tại.
- Dùng giờ hiện tại hoặc số ngẫu nhiên để tạo version/build key trong configuration.
- Gắn đường dẫn tuyệt đối máy cá nhân vào inputs nếu Gradle cần cache portable qua OS/máy.

Khi thực sự cần gọi công cụ ngoài trong configuration, dùng Gradle `providers.exec()`/`ValueSource` theo tài liệu cấu hình cache; nếu có thể, chuyển thao tác sang task action với inputs/outputs. Nếu cần giá trị git commit cho artifact, CI có thể truyền revision qua project property/provider, hoặc build logic dùng ValueSource theo quy tắc Gradle; không ép tất cả build trên máy developer phải có `git` executable trên `PATH`.

Để kiểm tra cache trên bài demo:

```bash
./gradlew writeEnvironmentManifest --configuration-cache
./gradlew writeEnvironmentManifest --configuration-cache
./gradlew writeEnvironmentManifest -PbuildTarget=ci --configuration-cache
```

Lần hai **có thể** reuse configuration cache khi cùng tasks, cùng inputs cấu hình và build/plugin tương thích. Lần ba đổi project property `buildTarget` nên Gradle có thể phải invalidate configuration state hoặc cập nhật input của task tùy thời điểm/provider. Hãy dựa vào log Gradle để phân biệt `Configuration cache entry reused`, `UP-TO-DATE` và build cache hit; ba hiện tượng này không có cùng ý nghĩa. Thay đổi `BUILD_ID` khi đã wire Provider vào task input giúp task nhận ra khác biệt dữ liệu.

## 12. CI: xác nhận build chạy trên máy sạch và nhiều hệ điều hành

CI tốt phải tự mô tả **JDK version, Gradle entrypoint, biến/cờ môi trường và task cần chạy**. Ví dụ GitHub Actions cho repo demo:

```yaml
name: Verify portable Gradle configuration

on:
  push:
  pull_request:

jobs:
  verify:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
    runs-on: ${{ matrix.os }}

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - uses: gradle/actions/setup-gradle@v4

      - name: Generate manifest (Linux/macOS)
        if: runner.os != 'Windows'
        env:
          BUILD_ID: ci-demo
        run: ./gradlew writeEnvironmentManifest -PbuildTarget=ci

      - name: Generate manifest (Windows)
        if: runner.os == 'Windows'
        shell: pwsh
        env:
          BUILD_ID: ci-demo
        run: .\gradlew.bat writeEnvironmentManifest -PbuildTarget=ci
```

Ví dụ workflow chạy task **của `build.gradle` ở phần 5**, không chạy release/deploy. Các runner được cấp `BUILD_ID` tường minh và gọi Wrapper đã commit. Trên Linux/macOS, script `gradlew` cần bit executable trong Git; trên Windows có `gradlew.bat`. Bản phân phối Gradle, plugin/JDK cần tương thích với runner và mạng hiện hành.

Các task Java thật như `test`/`build` chỉ tồn tại khi plugin tạo chúng; muốn kiểm chứng thêm thì đưa chúng vào workflow tương ứng. CI đa OS đặc biệt hữu ích để phát hiện path separator, case-sensitive file names, encoding, shell syntax, permission và timezone.

**Không dùng việc CI đang pass trên runner đã có cache làm bằng chứng duy nhất.** Khi điều tra lỗi phụ thuộc máy, thử runner sạch hoặc build với `--refresh-dependencies` nếu cần kiểm tra dependency metadata, và bảo đảm build không phụ thuộc vào secrets/registry chỉ một nhân viên có quyền. `--refresh-dependencies` không có nghĩa “xóa mọi cache và tải lại tất cả bytes”; đọc log để biết phần nào thực sự được resolve.

## 13. Một quy trình chuẩn hóa môi trường trong dự án có sẵn

**Bước 1 — liệt kê các giả định ngầm.** Tìm các dấu hiệu: đường dẫn `C:\Users\...`, `/Users/...`, `/home/name/...`, `System.getenv`, `System.getProperty("user.home")`, `new File(".")`, `local.properties`, `System.currentTimeMillis`, `new Date()`, `git` hoặc network call chạy trong configuration, repository được khai báo ở init script cá nhân.

**Bước 2 — phân loại input.** Biến nào là cấu hình dùng chung, biến nào là lựa chọn của invocation, biến nào là secret, biến nào là file input/output? Đừng dồn mọi thứ vào một file `gradle.properties` commit chung.

**Bước 3 — định nghĩa tên, kiểu và default.** Ví dụ `buildTarget ∈ {local, ci}`; local có thể mặc định `local`, nhưng deploy target phải được chọn tường minh. Với đường dẫn, mô tả nó có thể vắng mặt không, relative to root nào, và có cần tạo thư mục không.

**Bước 4 — chuyển dữ liệu vào Gradle Providers.** Dùng `providers.gradleProperty("...")`, `providers.environmentVariable("...")`, `providers.systemProperty("...")` và `providers.fileContents(...)` phù hợp. Nối Provider vào task property/input; tránh gọi `.get()` ở configuration khi chưa cần.

**Bước 5 — chuẩn hóa runtime.** Commit Wrapper, chọn Java toolchain, xác nhận JDK chạy Gradle, chính sách plugin repositories, dependency versions/lock và artifact verification.

**Bước 6 — viết tài liệu setup local + CI.** Nêu rõ command Bash/PowerShell, key bắt buộc, nơi cấp secrets, cách test; cho phép developer dùng user-home Gradle properties nhưng không yêu cầu “copy cấu hình từ máy A”.

**Bước 7 — kiểm chứng bằng môi trường mới.** Clone sạch trên máy/runner khác, chạy `./gradlew --version`, `./gradlew help`, task demo và project tests tương ứng. So sánh outputs dự kiến, không chỉ nhìn mã thoát `0`.

**Bước 8 — kiểm tra cache và thay đổi input.** Chạy hai lần cùng config, sau đó đổi đúng một input; quan sát task rerun/up-to-date, configuration cache hit/miss. Nếu đổi biến mà task vẫn bị xem là up-to-date dù output đáng ra khác, task đang thiếu input declaration hoặc logic phụ thuộc ngầm.

## 14. Lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân phổ biến | Hướng xử lý |
| --- | --- | --- |
| Build chỉ chạy trên laptop một developer | Đường dẫn user home/ổ cứng hardcode; file local chưa commit hoặc chưa cấp ở CI | Dùng `layout.projectDirectory`/`layout.buildDirectory`, khai báo required files; tài liệu hóa cách cấp input |
| Windows lỗi nhưng Linux pass | Shell syntax, separator, permission, path case hoặc file encoding | Dùng script Wrapper tương ứng, Gradle file APIs, CI matrix; tránh command shell tùy OS trong task action |
| CI compile bằng Java khác local | Gradle runtime/JDK toolchain không cố định | Pin Wrapper và toolchain; cấu hình Java version trên CI; kiểm tra compatibility |
| `JAVA_HOME` đúng mà Java compiler vẫn khác | Java toolchain của task được chọn độc lập | Kiểm tra `java.toolchain`, `javaToolchains` task và compiler/test runtime tương ứng |
| `-PbuildTarget=ci` không có hiệu lực | Script đọc `System.getenv("TARGET_ENV")` thay vì project property | Thống nhất một nguồn `providers.gradleProperty("buildTarget")` và test override |
| Root `gradle.properties` bị ghi đè | User-home `gradle.properties` hoặc `-P` có precedence cao | Kiểm tra nguồn property đang dùng, làm contract rõ ràng; CI cấp flag tường minh |
| Thêm `local.properties` mà Gradle không đọc | Gradle core không tự import file đó | Cần plugin/build logic đọc file hoặc dùng Gradle project property |
| Task báo `UP-TO-DATE` dù input môi trường đổi | Task đọc ngầm biến/file thay vì khai báo `@Input`/`@InputFile` | Nối Provider vào typed task property; kiểm tra inputs/outputs |
| Configuration cache không reuse | Configuration đọc nhiều env vars, chạy subprocess, phụ thuộc volatile input | Dùng narrow Providers, chuyển hoạt động sang task; xem Gradle CC report |
| Build offline chỉ thành công trên một máy | Dependency/plugin/JDK distribution đã cache local, CI chưa có | Khai báo repository/network, lock/version, cấp quyền mirror; kiểm tra clean environment |
| Maven repo xác thực lỗi ở CI | Credentials chỉ có trên laptop hoặc đã hardcode sai | Đưa credentials vào secret store/user-home; cấu hình quyền truy cập qua Gradle API |
| File sinh ra mang path/username cá nhân | Task dùng `user.home` hoặc absolute path trong nội dung output | Tách path runtime khỏi nội dung artifact, dùng relative paths và normalized inputs |
| Log lộ token | In toàn bộ project properties/env vars hoặc truyền token qua CLI | Giảm log, dùng secret manager, tránh command-line secrets và output chứa credentials |
| Test theo timezone/locale của máy | Test dựa vào timezone/default charset/locale của host | Cố định đầu vào phù hợp trong test task/app, ưu tiên clock/locale inject được, kiểm thử đa OS |

## 15. Checklist nghiệm thu một Gradle build portable

1. **Mọi người gọi cùng Wrapper**: đủ bốn tệp trong Git, version Gradle cố định và phù hợp plugin/JDK.
2. **JDK cần dùng được mô tả**: Java toolchain cho tasks và JVM chạy Gradle có yêu cầu rõ ràng.
3. **Root build không chứa đường dẫn cá nhân hoặc secret**; user-home config chỉ dành cho từng máy.
4. **Mỗi project property môi trường có tên, kiểu, nguồn, default hoặc validation**; các target nhạy cảm như production không được chọn ngầm.
5. **CLI `-P` và `ORG_GRADLE_PROJECT_*` được dùng có chủ ý**; người viết biết quy tắc precedence và có thể giải thích giá trị từ đâu ra.
6. **Task inputs/outputs được khai báo** qua Gradle properties/Providers/annotations; task không âm thầm đọc file, network hoặc env bên ngoài hợp đồng.
7. **Path đầu vào và output portable**, thuộc project/build layout hoặc thông số được cấu hình có căn cứ.
8. **Plugin và artifact repositories được khai báo**, không trông chờ cache hay init script riêng của một nhân viên.
9. **Local và CI có hướng dẫn nhất quán**: lệnh thực thi, required variables, secrets, test/build tasks; không yêu cầu copy file người khác.
10. **Đã chạy thử trên môi trường sạch và đổi input**: kết quả task thay đổi đúng, up-to-date/configuration cache phản ánh input thực tế.
11. **Không để secret lọt qua logs/artifacts/caches dùng chung**; quyền truy cập storage/CI được kiểm soát.
12. **Nếu nhiều OS được hỗ trợ, CI kiểm chứng ít nhất các OS quan trọng** và xác nhận line ending, filesystem case, JDK, encoding.

## Tài liệu chính thức để tra cứu

- [Gradle — Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html): nguồn và thứ tự ưu tiên của `-P`, `-D`, `gradle.properties`, `ORG_GRADLE_PROJECT_*`, JVM và biến môi trường.
- [Gradle — Providers and Properties](https://docs.gradle.org/current/userguide/properties_providers.html): cách truyền dữ liệu lazy, kết nối nguồn cấu hình tới task.
- [Gradle — Incremental Build and Task Inputs/Outputs](https://docs.gradle.org/current/userguide/incremental_build.html): khai báo file/value inputs, output và up-to-date.
- [Gradle — Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html): đọc environment, file, subprocess và yêu cầu với task actions.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): configuration cache so với build cache, đầu vào và bảo mật.
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html): chọn Java toolchain tách khỏi JVM chạy Gradle.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): pin Gradle version và chạy nhất quán qua các hệ điều hành.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): cố định phiên bản dependency khi cần build tái lập.

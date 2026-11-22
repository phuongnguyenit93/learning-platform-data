# Build tái lập và các nguồn biến động ngoài source code trong Gradle

## 1. Bài toán: cùng source nhưng khác artifact

Một team phát triển ứng dụng Java chạy `./gradlew build` trên cùng một commit. Máy developer tạo JAR với SHA-256 A, CI tạo JAR với SHA-256 B. Test đều pass, nhưng artifact không giống nhau về bytes. Có thể đã có **đầu vào biến động ngoài source code**: Gradle/JDK version, plugin, dependency graph, biến môi trường, ngày giờ hiện tại, cách liệt kê file, repository metadata, đường dẫn checkout, resource được tạo từ network hoặc ZIP entry metadata.

**Build reproducible** là build mà với **cùng tập input đã xác định** thì tạo ra output tương ứng giống nhau, lý tưởng **byte-for-byte identical**, dù chạy ở thời điểm hoặc máy khác. Tính chất này mạnh hơn “build chạy lại thành công”. Đặc biệt, hai JAR chứa Java classes tương đương nhưng timestamp hoặc thứ tự file ZIP khác nhau vẫn có thể mang hai SHA-256 khác nhau.

Bài học này thuộc phần **Khóa và xác minh** của Gradle. Sau khi học, bạn sẽ:

- Phân biệt reproducibility, repeatability, correctness, up-to-date checks và build cache.
- Lập danh mục những **input ngoài source** mà Gradle hoặc plugin có thể đọc.
- Kiểm soát Gradle Wrapper, Java toolchain và exact compiler environment.
- Hiểu khác biệt giữa **dependency locking** và **dependency verification**.
- Chuẩn hóa JAR/ZIP: entry order, timestamps, permissions và nội dung generated files.
- Khai báo `@Input`/`@OutputFile` cho custom tasks, dùng `ProviderFactory` với Gradle properties và environment variables.
- Viết project Java 17 + Gradle Kotlin DSL, sinh resource ổn định, tạo JAR chạy được và so sánh SHA-256 của hai clean builds.
- Chẩn đoán mismatch bằng report, diff và kiểm thử trên hai checkouts/CI runners độc lập.
- Tránh những “giải pháp giả” như ép cache trả lại output cũ hoặc tắt hoàn toàn việc xác minh.

## 2. Repeatable, reproducible và correct khác nhau thế nào?

| Khái niệm | Tiêu chí chính | Ví dụ |
| --- | --- | --- |
| **Repeatable** | Chạy lại ở môi trường gần như không đổi cho kết quả giống | Hai lần clean build trong cùng thư mục có JAR cùng hash |
| **Reproducible** | Cùng input thực sự, các thời điểm/máy độc lập cũng cho artifact có bytes giống | Hai CI runners xây cùng commit với pinned toolchain và cùng input tạo JAR có SHA-256 trùng |
| **Correct** | Artifact đáp ứng yêu cầu nghiệp vụ, test và behavior chính xác | Ứng dụng Java chạy đúng và kiểm thử thông qua |
| **Secure/trusted** | Inputs/artifacts không bị thay thế trái phép, nguồn được đánh giá tin cậy | Verification metadata, signatures và supply-chain review |

Một artifact có thể reproducible **nhưng chứa cùng bug** trên mọi máy. Hai artifacts cũng có thể chạy cùng chức năng nhưng khác bytes do một trường `Build-Time` trong manifest: khi đó chúng *functionally equivalent* nhưng không *byte-for-byte reproducible*. Xác minh dependency SHA-256 không tự chứng minh source code không có lỗi hoặc lỗ hổng.

### 2.1. Mô hình của một build

~~~text
artifact =
    Build(
        source + settings + build scripts,
        Gradle distribution + plugins,
        Java toolchain + compiler flags,
        dependency versions + artifact bytes,
        Gradle properties + OS environment + system properties,
        timezone + locale + encoding + wall-clock,
        file order + permissions + absolute paths,
        generated data + external API + network,
        task implementation + output serialization
    )
~~~

**Cùng Git commit chỉ cố định một phần** của các input đó. Mục đích không phải “khóa mọi biến môi trường trên máy”, mà xác định **biến nào ảnh hưởng output**, chọn chính sách kiểm soát và không đọc nguồn ngầm.

### 2.2. Bốn dấu hiệu không đủ để kết luận reproducible

- `BUILD SUCCESSFUL`: build hiện tại không gặp lỗi; không so sánh artifact với build khác.
- `UP-TO-DATE`: Gradle bỏ qua task vì fingerprints theo khai báo không đổi; chưa chứng minh task sẽ tạo lại bytes giống.
- `FROM-CACHE`: Gradle trả lại output task đã cache; task chưa thực thi lại.
- Hai SHA-256 trùng **trên cùng máy**: bằng chứng repeatability ở môi trường đó, chưa đủ chứng minh chéo máy/checkout.

Một phép kiểm tra thực sự nên có ít nhất hai lần **clean rebuild**, dùng `--no-build-cache` để tránh lấy kết quả cũ, so hash artifacts, rồi mạnh hơn nữa là thử **hai workspace độc lập**.

## 3. Bản đồ các nguồn biến động ngoài source

| Nguồn | Triệu chứng hoặc nguyên nhân | Cách kiểm soát |
| --- | --- | --- |
| Gradle version | Gradle 8 và Gradle 9 có defaults khác nhau cho archive | Dùng Wrapper và pin distribution |
| Gradle Wrapper integrity | Distribution hoặc wrapper JAR bị thay | Verify ZIP SHA-256 và Wrapper JAR |
| JDK vendor/version | Khác compiler, bytecode, debug info, tools | Java toolchain, pin exact vendor/update khi cần |
| JVM/compiler args | `-parameters`, `--release`, annotation processors khác | Định nghĩa flags trong build logic, review changes |
| Plugin versions | Plugin dynamic hoặc thay logic | Pin version, kiểm soát plugin repositories |
| Direct/transitive dependencies | `1.+`/`latest.release`/version conflict | Pin và dependency locking |
| Changing artifact | `-SNAPSHOT` có cùng version nhưng bytes thay | Tránh changing deps cho release, integrity verification |
| Repositories | Mirror thứ tự hoặc metadata khác | Repository policy, filters, trusted sources |
| OS env/project properties | `APP_CHANNEL`, `releaseChannel`, `LANG`, `TZ` | Explicit Providers và task inputs |
| Wall-clock/randomness | `Instant.now()`/`UUID.randomUUID()` | Không nhúng hoặc truyền seed/timestamp cố định |
| Directory traversal | `File.listFiles()` có thứ tự không ổn định | Sort normalized paths |
| Filesystem metadata | File timestamps, Unix modes, symlinks | Reproducible archive settings |
| Paths | `/home/dev/...` khác `C:\agent\...` | Tránh nhúng absolute path |
| Encoding/newlines | UTF-8 vs default charset, LF vs CRLF | UTF-8/LF tường minh và Git attributes |
| Network | API trả dữ liệu “latest” mỗi ngày | Snapshot/version/checksum dữ liệu |
| Generated code | Generator/schema/template version không pin | Pin generator và khai báo inputs |
| Untracked files | `.gitignore` không ngăn Gradle copy file | Clean checkout, source filters, input audit |
| Cache/hidden state | Cached output che nondeterminism | Clean uncached verification build |

Các nguy cơ này **không có cùng mức độ** cho mọi build. Project Java-only có thể không bị ảnh hưởng native compiler, trong khi một project đóng gói executable đa hệ điều hành khó đòi một file binary giống nhau trên Linux và Windows. Định nghĩa **target platform** trước khi so hash.

## 4. Cố định Gradle bằng Wrapper

### 4.1. Wrapper có tác dụng gì?

Gradle Wrapper gồm:

~~~text
project/
├── gradlew
├── gradlew.bat
└── gradle/
    └── wrapper/
        ├── gradle-wrapper.jar
        └── gradle-wrapper.properties
~~~

Nó thực thi bản Gradle được khai báo trong `gradle-wrapper.properties`, thay vì sử dụng một phiên bản ngẫu nhiên trong PATH. Với repo đã có Wrapper:

~~~bash
./gradlew --version
./gradlew clean build
~~~

Windows:

~~~bat
gradlew.bat --version
gradlew.bat clean build
~~~

Nếu repo **chưa có Wrapper**, bạn phải dùng bản Gradle cài sẵn để chạy `gradle wrapper` và commit các file cần thiết. Không chạy `./gradlew` ở một project mới chưa sinh Wrapper rồi coi “file not found” là lỗi Java.

### 4.2. distributionSha256Sum

`gradle/wrapper/gradle-wrapper.properties` chứa `distributionUrl`. Gradle Wrapper hỗ trợ key `distributionSha256Sum` để xác minh ZIP Gradle distribution khi nó được download.

Chính sách:

1. Chỉ định một bản Gradle cố định (ví dụ một bản 9.x **cụ thể**, không phải mơ hồ “latest”).
2. Lấy checksum chính thức của **đúng** distribution ZIP đó.
3. Cấu hình `distributionSha256Sum` bằng **64 ký tự hex thực tế**.
4. Commit Wrapper files, review khi upgrade.
5. Xác minh checksum của **`gradle-wrapper.jar` riêng**; nó không được tự động chứng minh đúng chỉ bởi checksum ZIP distribution.

Không ghi một SHA-256 giả để “đủ cấu hình”; Wrapper sẽ fail khi checksum không khớp. Xem [Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html) và danh sách checksum chính thức. Nếu distribution đã cache, cần hiểu wrapper verification chủ yếu được thực hiện lúc tải distribution mới.

### 4.3. Wrapper không pin tất cả

Dùng Wrapper **không tự** chọn exact JDK, khóa dependencies, kiểm tra SHA-256 của mọi thư viện, cố định env vars hoặc ngăn custom task đọc đồng hồ. Nó chỉ là **một lớp** của reproducibility.

## 5. Java toolchain và JDK thật được dùng

Kotlin DSL trong `build.gradle.kts`:

~~~kotlin
plugins {
    id("java")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Mẫu này yêu cầu Gradle dùng **Java 17 toolchain** cho những Java tasks thích hợp. Nếu không có JDK phù hợp và không được cấu hình provisioning, task có thể báo lỗi.

### 5.1. Gradle JVM khác Java toolchain

- **Gradle JVM** là JVM chạy Gradle daemon/client.
- **Toolchain JVM** là JDK được dùng cho `javac`/test/JavaExec theo task/plugin.

Hai bản có thể khác nhau nếu Gradle hỗ trợ bố trí đó. `java -version` của terminal chưa chắc là compiler thực sự dùng bởi `compileJava`. Kiểm tra `./gradlew --version`, cấu hình toolchain và build logs.

### 5.2. Pin Java 17 major đã đủ chưa?

Chưa chắc để tạo **identical bytes** giữa mọi machines. Cần cân nhắc exact vendor/update, compiler args, annotation processors và những công cụ ngoài JDK. Java 17 ở vendor A và Java 17 ở vendor B không phải một cam kết sản sinh classfile bytes giống nhau trong mọi tình huống.

Nếu release đòi kiểm chứng chặt chẽ, ghi nhận toolchain distribution chính xác/CI image và compiler arguments; chạy thử chéo môi trường. Java 17 toolchain trong bài thực hành là mức kiểm soát cần thiết cho học tập, không phải một chứng chỉ reproducible xuyên mọi JDK.

## 6. Khóa dependency versions để tránh resolution drift

### 6.1. Dynamic và changing versions

Ví dụ minh họa:

~~~kotlin
dependencies {
    implementation("org.example:core:1.+")
}
~~~

`org.example:core` chỉ là module giả dùng để giải thích cú pháp; không mặc định có trong repository. `1.+` là **dynamic version**. Hôm nay có `1.4`, ngày mai có `1.5`, thì cùng source có thể resolve dependency mới.

Một `-SNAPSHOT` hoặc changing dependency có thể có **cùng version** nhưng artifact bytes được publish lại. Locking một version không ngăn được nội dung của changing artifact thay đổi.

Cả transitive dependencies, constraints, platforms và metadata repository cũng có thể tác động selected versions. Đừng nhìn chỉ dòng direct dependency rồi kết luận toàn graph đã cố định.

### 6.2. Dependency locking trong Gradle

Kotlin DSL:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Groovy DSL:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Cấu hình này bật locking cho những project configurations mà Gradle có thể resolve. Không phải mọi `implementation` declarable bucket đều có lock state riêng và không phải mọi buildscript/plugin classpath được khóa tự động.

Tạo/cập nhật lock state theo workflow được review:

~~~bash
./gradlew dependencies --write-locks
~~~

Lệnh trên tạo/ghi những lockfiles như `gradle.lockfile` cho các **configurations thực sự được resolve**. Trong multi-project build, `dependencies` chạy tại root **không đảm bảo** đã resolve đủ tất cả subprojects; cần bao phủ các project/configurations quan trọng.

Dạng dữ liệu trong lockfile (trích đoạn minh họa, không phải module thật của bài lab):

~~~text
org.example:core:1.2.3=compileClasspath,runtimeClasspath
org.example:helper:4.5.6=runtimeClasspath
empty=annotationProcessor
~~~

**Commit lockfiles** vào VCS và review thay đổi. CI bình thường chạy build **không kèm `--write-locks`** để phát hiện resolution drift; chỉ chủ động cập nhật lock khi nâng dependency và đã review.

### 6.3. Giới hạn của locking

Dependency locking chủ yếu cố định **module versions** đã chọn, không tự:

- Xác minh bytes của một JAR cùng version.
- Ngăn nội dung `-SNAPSHOT` đổi.
- Pin plugins/buildscript classpath nếu chưa có chính sách riêng.
- Pin Gradle/JDK/time/locale/environment.
- Chứng minh mã nguồn thư viện an toàn.
- Đảm bảo output của task custom không nondeterministic.

**Câu hỏi mà locking trả lời:** “Project có resolve cùng **phiên bản** của các module đã lock không?”

## 7. Dependency verification: kiểm tra artifact bytes

Gradle hỗ trợ cấu hình ở:

~~~text
gradle/verification-metadata.xml
~~~

Một verification metadata đã được review có thể kiểm tra SHA-256 của artifacts và metadata được resolve bởi Gradle dependency management engine; PGP signatures có thể kiểm tra identity người ký khi trusted public keys được cấu hình đúng.

### 7.1. Bootstrap metadata

Sau khi xác định nguồn dependencies đáng tin:

~~~bash
./gradlew --write-verification-metadata sha256 help
~~~

Có thể yêu cầu checksums kèm PGP khi phù hợp:

~~~bash
./gradlew --write-verification-metadata sha256,pgp help
~~~

Gradle có thể resolve/download nhiều dependencies để thu thập metadata và tạo/cập nhật file. **Đây là bootstrap, không phải kiểm chứng nguồn đã sạch.** Nếu repository/cache đã bị thay trước lúc bootstrap, hash được ghi vẫn có thể thuộc artifact độc hại.

Quy trình an toàn:

1. Review `gradle/verification-metadata.xml` và các artifacts rủi ro cao.
2. Đối chiếu checksum với nguồn chính thức/đáng tin.
3. Với PGP, chọn trusted keys đúng; “có chữ ký” chưa đủ.
4. Commit file và review diff khi cập nhật dependency.
5. Điều tra `verification failed` thay vì luôn cập nhật hash để build pass.
6. Không lờ verification failure bằng cách tắt verification trong release CI.

### 7.2. Locking và verification khác nhau thế nào?

| Cơ chế | Mục đích | Không đảm bảo |
| --- | --- | --- |
| `gradle.lockfile` | Selected versions không đổi ngoài ý định | Artifact cùng version có bytes không đổi |
| `verification-metadata.xml` | Kiểm tra checksums/PGP theo trust metadata | Version resolution không trôi |
| Wrapper checksum | ZIP Gradle distribution không bị đổi lúc tải | Mọi plugins/JDK/artifacts đều đúng |
| Jar reproducibility settings | Order và timestamps của archive entries | Generated resource không nhúng đồng hồ |

Một build mạnh thường dùng **cả locking lẫn verification**, không chọn một thay cho cái kia. Dependency verification cũng không tự bảo vệ dữ liệu mà custom task tải bằng một HTTP client tùy ý. Gradle còn có những giới hạn với changing dependencies và artifacts do chính project build.

## 8. Reproducible JAR/ZIP trong Gradle

JAR là ZIP archive. Các nguyên nhân hash thay dù Java code như nhau:

- Timestamp của ZIP entries khác.
- File entries được thêm theo thứ tự khác.
- Permission metadata khác.
- `META-INF/MANIFEST.MF` nhúng build time/hostname.
- Resource/generated source bên trong thay bytes.
- Compiler/JDK output class khác.

### 8.1. Mặc định thay đổi từ Gradle 9

**Từ Gradle 9.0.0**, các `AbstractArchiveTask` như `Jar`, `Zip`, `War`, `Ear` mặc định tạo archives reproducible: thứ tự entries deterministic, timestamps chuẩn hóa và file/directory permissions cố định. Ở các bản Gradle cũ hơn, cần kiểm tra defaults và thường đặt cấu hình rõ.

Kotlin DSL tường minh:

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Groovy DSL:

~~~groovy
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Các tùy chọn này quản lý **metadata/thứ tự đóng gói**, không thay thế kiểm soát permissions trên Gradle cũ hoặc sửa được một file nội dung ngẫu nhiên.

### 8.2. Ngay cả JAR có entry order cố định vẫn có thể khác

Ví dụ một custom task sinh:

~~~kotlin
// Anti-pattern: nội dung file thay mỗi lần gọi task.
val buildTime = java.time.Instant.now().toString()
val generatedText = "build.time=" + buildTime
~~~

Nếu text này được đưa vào JAR, JAR khác bytes dù `isPreserveFileTimestamps=false`. Tương tự khi manifest chứa `Build-Time`, generated properties chứa absolute path hoặc UUID, hoặc classes do processor tạo không ổn định.

**Một artifact reproducible phải có nội dung từng entry reproducible**, không chỉ vỏ ZIP reproducible.

## 9. Kiểm soát thời gian và ngẫu nhiên

### 9.1. Đồng hồ không phải input ổn định

Các nguồn biến động gồm `Instant.now()`, `System.currentTimeMillis()`, `LocalDateTime.now()`, `UUID.randomUUID()`, random seed không cố định và file creation/modification timestamps.

Nếu business requirement **phải** có build timestamp, hãy xem nó là một input được xác định:

- Release pipeline có thể truyền `-PbuildEpochSeconds=...` cố định theo đợt release.
- Có thể dùng commit timestamp nếu xác định chính xác rule và commit được pin.
- Quy ước `SOURCE_DATE_EPOCH` hữu ích nếu tool/plugin hỗ trợ; nếu không, build logic phải **tự đọc và sử dụng** nó rõ ràng. Không giả định Gradle tự áp dụng biến này cho mọi task.

Khi timestamp input thực sự khác, output khác là **đúng theo định nghĩa** — reproducibility không đòi “hai input khác nhau phải cho cùng output”.

### 9.2. Randomness khi thực sự cần

Generator nên nhận seed tường minh và được khai báo `@Input`. Tránh dùng `new Random()` mặc định hoặc UUID ngẫu nhiên làm thông tin bên trong artifact. Nếu một ID phải được tạo một lần cho release, lưu ID đó như một input được review, đừng tự sinh lại mỗi build.

## 10. Environment, locale, timezone, encoding và newline

### 10.1. Đọc các nguồn đúng API

~~~kotlin
val channel = providers.gradleProperty("releaseChannel")
    .orElse("stable")

val label = providers.environmentVariable("BUILD_LABEL")
    .orElse("local")

val systemMode = providers.systemProperty("demo.mode")
    .orElse("default")
~~~

- `gradleProperty("releaseChannel")` tìm Gradle project property, ví dụ `-PreleaseChannel=preview` hoặc `gradle.properties`.
- `environmentVariable("BUILD_LABEL")` tìm OS environment variable của tiến trình Gradle; không tự parse `.env`.
- `systemProperty("demo.mode")` đọc JVM system property, khác hai namespace kia.

Chúng trả về `Provider<String>`. Nếu một task dùng chúng để sinh output, nối Provider vào typed `Property<String>` có `@Input` thay vì gọi `get()` sớm rồi capture giá trị ngầm trong `doLast`.

### 10.2. Timezone/locale

Một plugin/generator format `LocalDateTime.now()` hoặc số/ngày theo default `Locale` có thể tạo output khác. Những lựa chọn có chủ đích:

- UTC nếu cần timestamp định dạng không phụ thuộc timezone.
- `Locale.ROOT`/`Locale.US` khi serialize dữ liệu theo format cố định.
- Timestamp cố định từ input, **không** current wall-clock.
- Không để thông điệp/currency format theo user locale chảy vào artifact release nếu không phải tính năng.

### 10.3. Encoding và newline

~~~kotlin
target.writeText("release.channel=" + channel.get() + "\n", Charsets.UTF_8)
~~~

`Charsets.UTF_8` và `\n` làm bytes text rõ ràng. Với Java `Properties.load(InputStream)`, format properties theo quy tắc Java; nên dùng ASCII cho key/value trong ví dụ hoặc escape/encoder phù hợp nếu có Unicode phức tạp.

Có thể quản lý line endings trong Git, ví dụ `.gitattributes`:

~~~gitattributes
*.java text eol=lf
*.kts text eol=lf
*.properties text eol=lf
*.md text eol=lf
~~~

Đây là ví dụ policy cho loại file tương ứng, không bắt buộc áp dụng nếu dự án có đặc thù. Không cho các file binary chịu quy tắc text một cách vô ý. Nếu CI và máy developer checkout bytes khác, hash có thể khác vì file nội dung đã thực sự khác.

## 11. Những input Gradle không thể tự đoán

Gradle xác định up-to-date/cache dựa trên **inputs/outputs được khai báo**. Nếu task tự đọc `BUILD_LABEL`, một file local chưa khai báo hoặc một REST API rồi sinh output, cache key có thể không phản ánh dữ liệu ấy.

### 11.1. Sai: khai báo output nhưng bỏ sót input

~~~kotlin
tasks.register("badInfo") {
    val output = layout.buildDirectory.file("generated/bad.txt")
    outputs.file(output)

    doLast {
        val file = output.get().asFile
        file.parentFile.mkdirs()
        file.writeText(System.getenv("BUILD_LABEL") ?: "local")
    }
}
~~~

Đây là **anti-pattern minh họa**, không nên sao chép vào production. Task output phụ thuộc OS env nhưng không khai báo env value thành input. Gradle có thể bỏ qua task vì nhận định không có input nào đổi, hoặc cách truy cập trực tiếp trong task action gặp vấn đề Configuration Cache.

### 11.2. Đúng: custom typed task có @Input và @OutputFile

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction

abstract class LabelTask : DefaultTask() {
    @get:Input
    abstract val label: Property<String>

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun writeLabel() {
        val file = outputFile.get().asFile
        file.parentFile.mkdirs()
        file.writeText("label=" + label.get() + "\n", Charsets.UTF_8)
    }
}

tasks.register<LabelTask>("generateLabel") {
    label.set(
        providers.environmentVariable("BUILD_LABEL").orElse("local")
    )
    outputFile.set(layout.buildDirectory.file("generated/label.txt"))
}
~~~

**Điểm tốt:**

1. `ProviderFactory` xác định nguồn env.
2. `label` là task input được khai báo rõ.
3. Output path được khai báo, Gradle theo dõi nó.
4. `@TaskAction` chỉ đọc values từ task properties, không dựa Project API trực tiếp.
5. File text có encoding/newline ổn định.

Snippet này là một **phần cấu hình build script**, không phải Java program độc lập. Khi thiết kế cacheable task, còn phải đảm bảo task implementation deterministic và inputs đầy đủ; chỉ thêm `@Input` chưa khiến mọi task tự động đáng cache.

## 12. Dự án hoàn chỉnh Java 17: tạo JAR có output được xác định

Bài thực hành sau chạy được trong một project Gradle Kotlin DSL mới với JDK 17 và Gradle phù hợp. Nó **không có external module dependency**, nên việc kiểm chứng chủ yếu tập trung Java toolchain, task input, generated resource và archive settings. Sau đó có thể mở rộng locking/verification cho các project dùng thư viện ngoài.

### 12.1. Cây thư mục

~~~text
reproducible-jar-lab/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    └── main/
        └── java/
            └── demo/
                └── Main.java
~~~

### 12.2. settings.gradle.kts

~~~kotlin
rootProject.name = "reproducible-jar-lab"
~~~

### 12.3. build.gradle.kts hoàn chỉnh

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction
import org.gradle.api.tasks.bundling.AbstractArchiveTask
import org.gradle.api.tasks.bundling.Jar
import org.gradle.language.jvm.tasks.ProcessResources

plugins {
    id("java")
}

group = "demo"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

// Ổn định metadata và thứ tự entries của archive.
tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}

// Task tạo resource từ một input xác định, không đọc giờ hiện tại.
abstract class GenerateBuildInfo : DefaultTask() {
    @get:Input
    abstract val releaseChannel: Property<String>

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val target = outputFile.get().asFile
        target.parentFile.mkdirs()
        target.writeText(
            "release.channel=" + releaseChannel.get() + "\n",
            Charsets.UTF_8
        )
    }
}

val buildInfo = tasks.register<GenerateBuildInfo>("generateBuildInfo") {
    releaseChannel.set(
        providers.gradleProperty("releaseChannel").orElse("stable")
    )
    outputFile.set(
        layout.buildDirectory.file("generated/build-info/build-info.properties")
    )
}

// Nối output của task generator vào processResources.
tasks.named<ProcessResources>("processResources") {
    from(buildInfo)
}

tasks.named<Jar>("jar") {
    manifest {
        attributes["Main-Class"] = "demo.Main"
    }
}
~~~

**Giải thích luồng:**

~~~text
Gradle property releaseChannel (mặc định stable)
                 |
                 v
GenerateBuildInfo: @Input -> @OutputFile
                 |
                 v
build/generated/build-info/build-info.properties
                 |
                 v
processResources -> classes -> jar
                 |
                 v
build/libs/reproducible-jar-lab-1.0.0.jar
~~~

- `id("java")` tạo các task Java/`processResources`/`jar`.
- Java toolchain yêu cầu JDK 17.
- `AbstractArchiveTask` thiết lập thứ tự entries và timestamps deterministic.
- `GenerateBuildInfo` khai báo input `releaseChannel` và output file.
- `providers.gradleProperty("releaseChannel").orElse("stable")` cho giá trị mặc định ổn định.
- `from(buildInfo)` sử dụng task provider như source; Gradle nhận diện output file và dependency giữa generator với processResources.
- `manifest["Main-Class"]` cố định entry point của JAR; không nhúng timestamp/user/host.
- `processResources` tạo resource ở runtime classpath, nên Java class đọc được nó khi chạy JAR.

Lưu ý **không** thêm code đọc `Instant.now()` hoặc `System.getenv(...)` trực tiếp vào generator khi chưa khai báo input của nó. Cũng không cần `mavenCentral()` cho ví dụ này vì không có external library dependency.

### 12.4. Main.java chạy được với Java 17

Tạo `src/main/java/demo/Main.java`:

~~~java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();

        try (InputStream input =
                 Main.class.getResourceAsStream("/build-info.properties")) {
            if (input == null) {
                throw new IOException("Missing build-info.properties");
            }
            properties.load(input);
        }

        System.out.println("Hello reproducible build");
        System.out.println("channel=" +
                properties.getProperty("release.channel"));
    }
}
~~~

Mã Java hợp lệ với JDK 17. `getResourceAsStream` đọc resource ở root runtime classpath, không đọc file tạm bất kỳ của máy developer. Nếu thiếu resource, chương trình báo lỗi rõ ràng, tránh in `channel=null` rồi tưởng build thành công.

### 12.5. Chạy trên Gradle có sẵn

Từ thư mục `reproducible-jar-lab`:

~~~bash
gradle clean jar
java -jar build/libs/reproducible-jar-lab-1.0.0.jar
~~~

Stdout **chính xác của Java program**, khi không có project property `releaseChannel` nào ghi đè:

~~~text
Hello reproducible build
channel=stable
~~~

Không dự đoán toàn bộ log `gradle clean jar`: các task status và cảnh báo phụ thuộc phiên bản Gradle/môi trường. Đường dẫn JAR dự kiến dựa trên `rootProject.name` và `version` đã khai báo.

Nếu repository đã có Wrapper, dùng `./gradlew clean jar` trên Linux/macOS hoặc `gradlew.bat clean jar` trên Windows. Trong project mới **chưa có Wrapper**, dùng Gradle đã cài tương thích và tạo Wrapper riêng khi cần.

### 12.6. Kiểm tra SHA-256 của hai clean builds

Linux:

~~~bash
gradle --no-build-cache clean jar
sha256sum build/libs/reproducible-jar-lab-1.0.0.jar

gradle --no-build-cache clean jar
sha256sum build/libs/reproducible-jar-lab-1.0.0.jar
~~~

macOS:

~~~bash
gradle --no-build-cache clean jar
shasum -a 256 build/libs/reproducible-jar-lab-1.0.0.jar

gradle --no-build-cache clean jar
shasum -a 256 build/libs/reproducible-jar-lab-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
gradle --no-build-cache clean jar
(Get-FileHash .\build\libs\reproducible-jar-lab-1.0.0.jar -Algorithm SHA256).Hash

gradle --no-build-cache clean jar
(Get-FileHash .\build\libs\reproducible-jar-lab-1.0.0.jar -Algorithm SHA256).Hash
~~~

**Kết quả cần kiểm tra:** Hai giá trị SHA-256 **nên trùng** nếu nội dung đầu vào, JDK compiler, Gradle và archive behavior không đổi. Không cung cấp một hash giả làm “expected stdout”: byte-level hash phải được tính trên artifact thực tế.

Tại sao `--no-build-cache` và `clean`?

- `clean` buộc build tạo lại những outputs trong build directory.
- `--no-build-cache` tránh việc lấy output task cũ từ build cache và tuyên bố “reproducible” trong khi task chưa chạy lại.
- Thử trong cùng thư mục mới chỉ xác minh **repeatability**; sau đó hãy so sánh hai checkouts khác đường dẫn hoặc CI runners độc lập để phát hiện hidden inputs.

### 12.7. Thay đổi đầu vào có chủ ý

Chạy:

~~~bash
gradle --no-build-cache clean jar -PreleaseChannel=preview
java -jar build/libs/reproducible-jar-lab-1.0.0.jar
~~~

Stdout Java:

~~~text
Hello reproducible build
channel=preview
~~~

Giá trị resource đã đổi từ `stable` sang `preview`. Vì input **khác**, hash JAR khác là điều có thể mong đợi và **không phải** thất bại reproducibility. Lặp lại cùng `-PreleaseChannel=preview` trong điều kiện tương đương thì artifact phải tái lập được.

### 12.8. Kiểm tra nội dung archive

~~~bash
jar --list --file build/libs/reproducible-jar-lab-1.0.0.jar
~~~

Cần tìm các entries:

~~~text
META-INF/MANIFEST.MF
demo/Main.class
build-info.properties
~~~

Archive có thể còn directory entries như `META-INF/`, `demo/`; **đoạn trên không phải toàn bộ output** của `jar --list`. Muốn so sánh hai JAR khác hash, kiểm tra từng entry và metadata chứ không chỉ đếm file.

Kiểm tra generated resource:

~~~bash
cat build/generated/build-info/build-info.properties
~~~

Với default input, stdout:

~~~text
release.channel=stable
~~~

Trên Windows PowerShell có thể thay bằng `Get-Content .\build\generated\build-info\build-info.properties`.

### 12.9. Kiểm tra Java trực tiếp bằng javac/java

Java source dùng resource, nên khi chạy **không qua Gradle** cần tự tạo resource đó trên classpath.

Linux/macOS:

~~~bash
mkdir -p out
javac -d out src/main/java/demo/Main.java
printf 'release.channel=stable\n' > out/build-info.properties
java -cp out demo.Main
~~~

Stdout chính xác:

~~~text
Hello reproducible build
channel=stable
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -d out src\main\java\demo\Main.java
Set-Content -Path out\build-info.properties -Value "release.channel=stable" -Encoding Ascii
java -cp out demo.Main
~~~

Stdout giống trên. Các lệnh `javac`/`java` này chỉ kiểm tra mã Java/resource; **không kiểm tra Gradle Kotlin DSL, dependency graph hoặc reproducibility của JAR**. Dùng Gradle `jar` và hash để xác minh điều đó.

### 12.10. Hai checkouts độc lập

Để thử reproducibility chặt hơn:

1. Commit build scripts, Java source, settings và Wrapper files.
2. Checkout cùng commit vào hai thư mục khác nhau hoặc hai CI agents.
3. Dùng cùng Gradle distribution, Java compiler/toolchain, project property `releaseChannel` và môi trường cần thiết.
4. Chạy clean build **không build cache** ở mỗi workspace.
5. Lấy SHA-256 của hai JAR thành phẩm.
6. Nếu khác, so sánh contents/metadata từng entry.
7. Ghi nhận exact Gradle/JDK/OS/tool versions, không chỉ Git SHA.
8. Khi sửa được, thêm bước CI regression để phát hiện nondeterminism tái diễn.

Không so sánh binary của Linux target với binary của Windows target rồi kết luận build lỗi chỉ vì hashes khác. Định nghĩa target khi so sánh.

## 13. Những nguồn nondeterminism trong generator và filesystem

### 13.1. Thứ tự liệt kê file

Java `File.listFiles()` không bảo đảm một thứ tự trả về ổn định trên mọi filesystem. Generator dùng thứ tự duyệt ấy để viết JSON/index có thể tạo bytes khác.

Đoạn minh họa không độc lập:

~~~java
File[] children = directory.listFiles();
if (children != null) {
    Arrays.sort(children, Comparator.comparing(File::getName));
    for (File child : children) {
        // Serialize theo thứ tự đã sắp xếp.
    }
}
~~~

Đoạn này giả định có biến `directory` và imports `java.io.File`, `java.util.Arrays`, `java.util.Comparator`. Với nhiều folder con hoặc Unicode/case differences, cần tiêu chí sort theo **normalized relative path** để ổn định hơn.

### 13.2. Absolute paths và checkout location

Ví dụ developer build tại:

~~~text
/home/dev/work/app
~~~

còn CI:

~~~text
/workspace/runner/job-123/app
~~~

Nếu file sinh chứa đường dẫn tuyệt đối, hai artifacts khác bytes dù Git commit giống. Đừng nhúng workspace path vào manifest, source map hay generated text **trừ khi đó là một input nghiệp vụ có chủ đích**. Đối với task fingerprints và relocatable build cache, Gradle có path sensitivity/normalization riêng; không nên tự lấy một giá trị đường dẫn tuyệt đối chỉ để gắn vào output.

### 13.3. Case-sensitive filesystem và executable permissions

`Config.json` và `config.json` có thể cùng tồn tại trên filesystem phân biệt hoa/thường nhưng xung đột ở môi trường khác. Native packaging, executable scripts, symlinks và Unix file permissions cũng có thể thay đổi artifact. Gradle 9 chuẩn hóa permissions của archive tasks mặc định, nhưng **không** có nghĩa mọi plugin/native archive đều byte-for-byte identical trên mọi OS.

### 13.4. Data từ network

Một task codegen gọi `https://api.example.test/schema/latest` có thể nhận schema khác giữa hai lần build. Đây là **URL giả để minh họa**, không phải endpoint cần truy cập. Cách cải thiện:

- Pin schema version hoặc snapshot schema vào repo.
- Lưu checksum và verify input artifacts.
- Pin version code generator.
- Khai báo schema/template/generator options là inputs.
- Không fetch “latest” ngầm khi release.
- Tránh tải secrets hoặc dữ liệu nhạy cảm vào published artifact.

### 13.5. Git ignored nhưng vẫn có thể ảnh hưởng

`.gitignore` không làm Gradle bỏ qua file khi `Copy`/`processResources` quét nguồn. Một `local.properties` không commit nhưng nằm trong `src/main/resources` vẫn có thể được đóng vào JAR tại máy developer, trong khi CI sạch không có. Hãy kiểm tra source filters và build trong clean checkout; không đưa secret vào resource JAR.

## 14. Build cache và Configuration Cache không thay thế reproducibility

| Cơ chế | Tác dụng | Không tự đảm bảo |
| --- | --- | --- |
| Up-to-date checks | Task bị skip khi input/output fingerprints thích hợp không đổi | Rebuild thật tạo cùng bytes |
| Build Cache | Lấy lại output tasks có cache key trùng | Task implementation không nondeterministic |
| Configuration Cache | Tái sử dụng kết quả configuration/task graph | Java/resource output deterministic |
| Dependency Locking | Ghim selected module versions | Artifact bytes/timestamps/toolchain không đổi |
| Dependency Verification | Check expected hash/signature cho artifacts phù hợp | Source/generator/time/env đúng |
| Reproducible archives | Điều khiển archive order/timestamps/metadata | Nội dung từng entry không tự sinh random |

### 14.1. Cache có thể che lỗi

Nếu một task sinh file với `Instant.now()` nhưng Gradle cho `FROM-CACHE`, output được lấy từ lần cũ. Hai hashes có thể giống dù task khi chạy thật tạo hai giá trị khác nhau. Đó là lý do phép thử reproducibility cần `--no-build-cache` cùng clean rebuild.

### 14.2. Configuration Cache và environment

Gradle có thể theo dõi environment/system properties được đọc ở configuration làm configuration inputs. Nhưng một task chỉ dùng chúng lúc execution mà không khai báo `@Input` vẫn có nguy cơ kết quả/điều kiện caching sai. Dùng `providers.environmentVariable(...)` và `Property<T>` để nối input vào task.

### 14.3. Có phải tắt cache trong toàn bộ CI?

Không. Với tasks được khai báo đúng, cache tăng tốc build mà không làm giảm tính đúng đắn. Tổ chức một pipeline daily dùng cache, cộng một job **rebuild independent** cho release hoặc định kỳ. Không xóa sạch mọi Gradle User Home mỗi lần chỉ để “cảm thấy sạch”; cần kiểm soát input và kiểm chứng artifact mới.

## 15. Repositories, plugins và nguồn artifact

### 15.1. Repository metadata có thể thay đổi

Cùng `group:name:version` có thể được trả về từ những repositories khác nhau. Nếu chúng có metadata hoặc artifact bytes không nhất quán, classpath có thể khác theo repository order/cache/network. Khi thiết kế release:

- Chỉ dùng repositories/mirrors tin cậy.
- Cấu hình repository content filters hoặc exclusive content cho namespaces khi cần.
- Review `pluginManagement` và `dependencyResolutionManagement` trong settings.
- Pin plugin versions.
- Pin/lock module versions theo scope đúng.
- Dùng dependency verification để kiểm tra bytes.
- Không coi `mavenLocal()` là nguồn đáng tin đồng nhất trong CI/release; artifacts tại đó thay theo máy.

### 15.2. Plugins và build logic cũng là input

Dù Java source không đổi, plugin version mới có thể đổi tasks, compiler flags, generated files, ordering hoặc defaults. `buildSrc`, convention plugins và included builds là build logic cần version-control và kiểm tra. Dependency locking project configurations không đương nhiên khóa tất cả plugin management/buildscript classpaths.

### 15.3. Changing dependencies

Một artifact dạng `-SNAPSHOT` hoặc dependency được đánh dấu changing có thể bị publish lại với **cùng tọa độ**. Lock selected version không đủ; integrity checks đối với changing artifacts còn có giới hạn. Release cần ưu tiên immutable versions và repository policy cho phép truy nguyên bytes.

### 15.4. Dependency verification khác security scan

Một checksum trùng chứng minh downloaded bytes khớp giá trị đã được tin cậy, không nói dependency không có CVE hoặc code độc hại. Cần tách artifact integrity, provenance, vulnerability scanning, license review và reproducible build checking thành các bước bổ sung nhau.

## 16. Quy trình CI cho release reproducibility

### 16.1. Pipeline build thông thường

1. Checkout đúng commit và submodules.
2. Xác minh Wrapper/distribution checksums.
3. Dùng JDK toolchain theo chính sách.
4. Dùng lockfiles và verification metadata đã commit.
5. Chạy `./gradlew build` với cache thích hợp cho tốc độ.
6. Chạy test và lưu artifact.
7. Ghi manifest/provenance riêng của release: commit, JDK, Gradle, artifact SHA.

### 16.2. Job kiểm chứng độc lập

1. Dùng cùng commit + target + values của build properties/env thực sự ảnh hưởng output.
2. Lấy hai clean workspaces, không copy `build/` từ workspace cũ.
3. Build ở mỗi workspace với `--no-build-cache`.
4. Tính SHA-256 của **cùng loại artifact**.
5. So sánh hashes.
6. Nếu khác, diff archives và tìm entry gây mismatch.
7. Chỉ sửa nguồn biến động sau khi đã xác định bằng chứng.
8. Khi hash trùng, kết hợp với tests/security checks; hash trùng không thay thế chất lượng.

### 16.3. Phân tích mismatch

~~~bash
jar --list --file first.jar
jar --list --file second.jar
sha256sum first.jar second.jar
~~~

Lệnh `jar --list` **không so sánh bytes** của các entries; chỉ cho danh sách để bắt đầu. Có thể giải nén hai JAR vào hai folder riêng, hash từng entry hoặc dùng công cụ archive diff.

| Vị trí khác nhau | Hướng điều tra |
| --- | --- |
| Chỉ ZIP metadata | Timestamps, permissions, entry order, plugin/archive defaults |
| `META-INF/MANIFEST.MF` | Build time, version, commit metadata, username/host |
| `build-info.properties` | Gradle property, env var, newline/encoding |
| `.class` | JDK/compiler/update, codegen, annotation processor, flags |
| File thêm/bớt | Untracked resources, include/exclude patterns, task outputs |
| Dependency JAR | Repositories, version resolution, lock/verification |
| Generated index/JSON | Filesystem ordering, map iteration, serializer, locale |

Nếu output khác giữa hai OS, so sánh thêm file modes, paths, line endings và platform-specific tasks.

### 16.4. Provenance nên tách khỏi bytes của artifact khi có thể

Runner ID, build URL, current time và absolute workspace path rất hữu ích để truy vết, nhưng nếu nhúng vào JAR, hai independent builds sẽ khác bytes. Có thể đặt thông tin provenance ở **artifact/attestation bên ngoài** JAR, còn JAR chỉ chứa những input đã được xác định. Commit SHA có thể là input hợp lệ nếu được pin và xử lý nhất quán.

## 17. Các sai lầm thường gặp và cách sửa

### Lỗi 1. Dùng Gradle cài trên máy thay vì Wrapper

Máy A và CI có Gradle khác version, đặc biệt khác mặc định archive ở Gradle 9.

**Sửa:** Pin Wrapper và kiểm tra distribution/JAR integrity.

### Lỗi 2. Dùng “Java 17” nhưng không kiểm tra compiler thật

`java -version` có thể khác toolchain `compileJava` dùng.

**Sửa:** Đọc Gradle toolchain configuration, JVM chạy Gradle, JDK vendor/update và compiler flags.

### Lỗi 3. Dynamic version hoặc changing module

`1.+`, `latest.release`, `-SNAPSHOT` thay theo repository.

**Sửa:** Pin versions, lock dependency graph, tránh changing versions khi release.

### Lỗi 4. Nghĩ gradle.lockfile đã đảm bảo JAR bytes

Lockfile chỉ lưu selected versions.

**Sửa:** Review `verification-metadata.xml`, SHA-256/PGP artifacts và repository policy.

### Lỗi 5. Bootstrap verification metadata mà không review

Artifact không đáng tin được ghi hash như expected value.

**Sửa:** Đối chiếu nguồn đáng tin và code review mọi metadata changes.

### Lỗi 6. Nhúng timestamp vào MANIFEST.MF

Archive entries deterministic nhưng nội dung manifest khác.

**Sửa:** Bỏ trường thời gian hoặc dùng timestamp input được pin.

### Lỗi 7. Generated resource chứa hostname/absolute path

Hai workspace khác location nên JAR SHA khác.

**Sửa:** Tránh nhúng dữ liệu không phải phần semantics của release.

### Lỗi 8. Dùng default charset/timezone

Text resource và formatted dates khác theo OS/locale.

**Sửa:** Explicit UTF-8/LF/UTC và stable locale khi serializing.

### Lỗi 9. File.listFiles() không sort

Generated file order khác giữa máy.

**Sửa:** Sort theo relative path chuẩn hóa, không dựa filesystem traversal order.

### Lỗi 10. Dùng cache làm phép thử

`FROM-CACHE` trả output cũ, chưa thực thi lại task.

**Sửa:** Clean rebuild độc lập và `--no-build-cache`.

### Lỗi 11. Không khai báo env var là task input

Task dùng `BUILD_LABEL` nhưng Gradle không biết nó ảnh hưởng output.

**Sửa:** `@Input Property<String>` nối từ `providers.environmentVariable(...)`.

### Lỗi 12. Tưởng SOURCE_DATE_EPOCH tự áp dụng

Custom task vẫn dùng `Instant.now()`.

**Sửa:** Xác nhận support hoặc đọc `SOURCE_DATE_EPOCH` như input tường minh và dùng nó khi sinh data.

### Lỗi 13. Build đọc file untracked/ignored

Máy developer có `local.properties`, CI không có.

**Sửa:** Clean checkout, nguồn tài nguyên rõ, không copy secrets vào artifact.

### Lỗi 14. CI tự --write-locks hằng lần

Trôi dependency được ghi đè thay vì phát hiện.

**Sửa:** Chỉ update locks qua thay đổi đã review, CI thường dùng lock state committed.

### Lỗi 15. So sánh binary khác target

Native artifacts Linux/Windows khác dù source như nhau.

**Sửa:** Chọn target platform tương ứng trước khi so hash; Java-only JAR vẫn cần kiểm chứng JDK/archive/input.

### Lỗi 16. Nondeterministic generator đọc latest API

Schema/asset được cập nhật không qua Git.

**Sửa:** Pin generator và schema, lưu checksum/snapshot, khai báo input file.

### Lỗi 17. Chỉ thử hai lần cùng workspace

Không phát hiện absolute path/hostname thay đổi theo checkout.

**Sửa:** So hai workspaces/agents độc lập với cùng input spec.

### Lỗi 18. Thấy hai JAR cùng hash và kết luận code an toàn

Reproducibility không đồng nghĩa correctness hay supply-chain trust.

**Sửa:** Vẫn phải test, review dependencies, kiểm tra integrity/security và provenance.

## 18. Bài tập thực hành có đáp án

### Bài 1. Phân biệt correct và reproducible

Hai JAR chạy như nhau nhưng khác ZIP timestamps. Chúng có byte-for-byte reproducible không?

**Đáp án:** Không. Chúng có thể tương đương chức năng nhưng SHA-256 khác; cần chuẩn hóa archive metadata.

### Bài 2. Đổi đúng input

Lab chạy lần 1 với `releaseChannel=stable`, lần 2 với `-PreleaseChannel=preview`. Hash khác có chứng minh lỗi?

**Đáp án:** Không. Input thực sự thay đổi nên generated resource thay bytes hợp lệ. So hash khi **cùng input values**.

### Bài 3. Locking và verification

Version module giữ nguyên nhưng artifact bị thay bytes. Cơ chế nào quan trọng?

**Đáp án:** Dependency verification SHA-256/PGP theo metadata tin cậy; locking chỉ giúp giữ selected version.

### Bài 4. Hash giống do cache

Lần 2 Gradle báo `FROM-CACHE` rồi SHA trùng. Có đủ bằng chứng?

**Đáp án:** Không. Task không chạy lại. Dùng clean `--no-build-cache` và so bytes.

### Bài 5. Dùng clock trong task

Task tạo `build-info.properties` có `Instant.now()`. Archive flags đã chuẩn hóa. SHA có ổn định?

**Đáp án:** Không nếu file content khác giữa các lần. Phải bỏ hoặc pin timestamp input.

### Bài 6. JDK khác vendor

Cả hai chạy Java 17 nhưng khác vendor/update. Có thể cam kết hash giống?

**Đáp án:** Không cam kết chung. Pin toolchain cụ thể và thử byte-level; plugin/processor/compiler flags cũng cần kiểm tra.

### Bài 7. Env var ảnh hưởng output

Task tạo file từ `BUILD_LABEL`. Cách khai báo đúng?

**Đáp án:** `providers.environmentVariable("BUILD_LABEL")` nối vào `@Input Property<String>`, output là `@OutputFile`. Không chỉ gọi `System.getenv` bên trong `doLast`.

### Bài 8. Dynamic version

`implementation("x:y:1.+")` build hôm nay chọn 1.4, ngày mai chọn 1.5. Cần làm gì?

**Đáp án:** Pin version/lock selected graph; với release cần kiểm soát dependency artifact integrity và repository metadata.

### Bài 9. Wrapper integrity

`distributionSha256Sum` có bảo vệ chính `gradle-wrapper.jar` không?

**Đáp án:** Không. Kiểm tra Wrapper JAR riêng với checksum chính thức hoặc workflow CI validation; distribution ZIP checksum bảo vệ một đối tượng khác.

### Bài 10. SHA của project lab

Chạy `java -jar build/libs/reproducible-jar-lab-1.0.0.jar` sau build mặc định sẽ in gì?

**Đáp án:**

~~~text
Hello reproducible build
channel=stable
~~~

Khi build với `-PreleaseChannel=preview`:

~~~text
Hello reproducible build
channel=preview
~~~

### Bài 11. Test mạnh hơn

Hai lần build cùng folder cho hash trùng. Bước kiểm tra tiếp?

**Đáp án:** Hai checkouts/agents độc lập cùng commit và controlled Gradle/JDK/dependency/property inputs, clean uncached build, so SHA của cùng artifact.

### Bài 12. File ignored nhưng bị copy

Local có `src/main/resources/secrets.properties` nằm trong `.gitignore`, CI không có. Vì sao JAR khác?

**Đáp án:** Git ignore không ngăn Gradle copy file. Nên loại secrets khỏi resources, kiểm tra source filters/clean checkout và không đóng gói credential.

## 19. Checklist áp dụng cho release

| Hạng mục | Đã kiểm soát khi... |
| --- | --- |
| Source | Commit, submodules, generated inputs và untracked files rõ ràng |
| Gradle | Wrapper pin version, distribution và Wrapper JAR được xác minh |
| Toolchain | JDK 17/target, vendor/update/flags có chính sách |
| Plugins | Versions pin, plugin repositories tin cậy |
| Dependencies | Versions được lock; không dùng changing/dynamic ngoài chủ ý |
| Integrity | Verification metadata reviewed và committed |
| Repositories | Không có mirror/metadata ambiguity |
| Environment | Mọi env/project property ảnh hưởng output được khai báo input |
| Time/randomness | Không đọc clock/UUID tự do hoặc có seed/timestamp cố định |
| Locale/encoding | Text serializer và newline/charset chuẩn hóa |
| Filesystem | File traversal order, modes, paths được chuẩn hóa |
| Archive | Reproducible entry order/timestamps/metadata |
| Generated files | Generator version/schema/templates được pin |
| Build test | Hai clean uncached builds được so SHA-256 |
| Functional test | Java/test/integration vẫn phải pass |
| Security | Checksums, provenance, review và không nhúng secrets |

**Kết luận:** **Một build reproducible phải xác định và kiểm soát toàn bộ nguồn ảnh hưởng output**, không chỉ Java source. Trong Gradle, kết hợp Wrapper, Java toolchain, dependency locking, dependency verification, reproducible archives, đúng `@Input`/`@OutputFile` và CI clean-build hash comparison. Nếu artifact bytes đổi, hãy lần ra **input đã biến động** thay vì đoán Gradle “không ổn định”.

## 20. Tài liệu chính thức

- [Gradle — Working with Files (Reproducible archives)](https://docs.gradle.org/current/userguide/working_with_files.html) — archive order, timestamps, permissions; mặc định Gradle 9.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html) — `lockAllConfigurations`, `--write-locks` và lock state.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html) — SHA-256, PGP và `verification-metadata.xml`.
- [Gradle — Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html) — version pin, distribution SHA-256 và Wrapper JAR verification.
- [Gradle — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html) — inputs, outputs và up-to-date behavior.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html) — task cache keys và output reuse.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html) — reuse task configuration, không phải reproducibility guarantee.
- [Gradle — Build Environment](https://docs.gradle.org/current/userguide/build_environment.html) — environment/project/system properties.
- [Gradle — Upgrading to Gradle 9](https://docs.gradle.org/current/userguide/upgrading_major_version_9.html) — archive tasks reproducible theo mặc định.
- [Reproducible Builds](https://reproducible-builds.org/) — nguyên tắc byte-for-byte reproducibility.

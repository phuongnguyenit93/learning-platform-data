# Thiết lập archive name, version, classifier và nội dung trong Gradle

## 1. Mục tiêu và bối cảnh

Trong Gradle, đóng gói không chỉ là chạy `jar` rồi nhận một file ở `build/libs`. Một build có thể cần JAR chứa class Java, ZIP chứa tài liệu, TAR.GZ cho máy Linux, JAR source, Javadoc JAR hoặc artifact có classifier riêng. Tên file phải nhất quán với version phát hành, nội dung phải đúng, và task tiêu thụ phải tìm được file ngay cả khi tên hoặc thư mục output thay đổi.

Bài học này làm rõ **archive name, version, classifier và contents**, thuộc nhóm Đóng gói của Gradle. Sau khi học, bạn có thể:

- Giải thích cách Gradle ghép `archiveBaseName`, `archiveAppendix`, `archiveVersion`, `archiveClassifier`, `archiveExtension` thành filename.
- Dùng `archiveFileName` để ghi đè tên hoàn chỉnh và biết hệ quả của việc này.
- Phân biệt `project.version`, archive version, manifest version và Maven publication version.
- Đặt `destinationDirectory` đúng, dùng `archiveFile` Provider để nối output giữa các tasks.
- Quyết định nội dung archive bằng `from`, `into`, `include`, `exclude` và `CopySpec`.
- Tạo JAR chạy được từ **Java 17** với `Main-Class`, resource và nội dung bổ sung; tạo ZIP tài liệu riêng.
- Hiểu `DuplicatesStrategy`, reproducible archives, source JAR/Javadoc JAR và giới hạn của classifier `all`.
- Tạo TAR.GZ với `Tar` và compression đúng, không chỉ đổi extension.
- Kiểm tra artifact bằng `jar --list`, `java -jar`, SHA-256 và Maven publication metadata.
- Chẩn đoán lỗi thiếu class/resource, tên sai, output bị ghi đè và vô tình đóng gói secrets.

Ví dụ sử dụng **Gradle Kotlin DSL** và Gradle Wrapper. Các đoạn code được phân biệt rõ giữa **file đầy đủ chạy độc lập** và **mảnh cấu hình thay thế**. Trên Windows PowerShell dùng `.\gradlew.bat` thay cho `./gradlew`.

## 2. Quy tắc đặt tên mặc định của `AbstractArchiveTask`

Gradle dựa trên `AbstractArchiveTask` để mô hình hóa các archive tasks như `Jar`, `Zip` và `Tar`. Nếu không chỉ định `archiveFileName` trực tiếp, tên archive được tạo theo mẫu:

~~~text
[archiveBaseName]-[archiveAppendix]-[archiveVersion]-[archiveClassifier].[archiveExtension]
~~~

Những thành phần trống **không** tạo ra dấu gạch nối dư. Ví dụ:

| Base | Appendix | Version | Classifier | Extension | Tên kết quả |
| --- | --- | --- | --- | --- | --- |
| `orders` | trống | `1.2.3` | trống | `jar` | `orders-1.2.3.jar` |
| `orders` | `cli` | `1.2.3` | `demo` | `jar` | `orders-cli-1.2.3-demo.jar` |
| `orders` | trống | `1.2.3` | `sources` | `jar` | `orders-1.2.3-sources.jar` |
| `orders` | `docs` | `1.2.3` | `manual` | `zip` | `orders-docs-1.2.3-manual.zip` |
| `orders` | trống | trống | `nightly` | `zip` | `orders-nightly.zip` |

**Tên task không tự định nghĩa filename.** Task `tasks.register<Zip>("createDocs")` không mặc nhiên tạo `createDocs.zip`. Tên archive đến từ các properties/conventions bên trên.

### Các properties cần nhớ

| Property | Kiểu Gradle | Vai trò |
| --- | --- | --- |
| `archiveBaseName` | `Property<String>` | Phần tên cơ sở, thường lấy từ project name hoặc `base.archivesName`. |
| `archiveAppendix` | `Property<String>` | Phần thêm sau base, ví dụ `cli`/`docs`. |
| `archiveVersion` | `Property<String>` | Phần version trong tên **archive file**. |
| `archiveClassifier` | `Property<String>` | Phân loại artifact, ví dụ `sources`, `javadoc`, `linux`. |
| `archiveExtension` | `Property<String>` | Đuôi file, như `jar`/`zip`/`tar.gz`. |
| `archiveFileName` | `Property<String>` | Filename hoàn chỉnh, có thể ghi đè công thức ghép. |
| `destinationDirectory` | `DirectoryProperty` | Thư mục chứa archive **bên ngoài**. |
| `archiveFile` | `Provider<RegularFile>`, chỉ đọc | Output file = directory + filename. |

Các properties dùng `Property.set(...)`, có thể giữ thông tin qua Providers. Không nên coi chúng là những String global để tính path cứng khắp build.

### Convention từ Base/Java plugin

- `base.archivesName` mặc định thường là `project.name`.
- `archiveVersion` theo `project.version`; khi project không có version cụ thể, phần version có thể bị lược bỏ.
- `archiveAppendix` và `archiveClassifier` thường trống khi chưa override.
- `Jar`/`War` của Java ecosystem thường xuất ra `build/libs`.
- `Zip`/`Tar` dạng distribution thường xuất ra `build/distributions`.
- `archiveExtension` phụ thuộc task và compression; không có một extension dùng chung.
- Plugin khác hoặc chính task có thể thay conventions, nên **kiểm tra output thực tế** thay vì đoán theo default.

Gradle cung cấp DSL cấp project:

~~~kotlin
base {
    archivesName = "company-product"
    libsDirectory = layout.buildDirectory.dir("company-libs")
    distsDirectory = layout.buildDirectory.dir("company-dist")
}
~~~

Đây là **mảnh cấu hình** cho project có Base plugin hoặc plugin áp Base (như Java). Nó thay conventions cho archive tasks phù hợp; nếu một task đã `archiveBaseName.set(...)` hoặc `destinationDirectory.set(...)` cụ thể, giá trị tường minh của task có thể thắng convention chung.

## 3. Archive properties khác danh tính project/Maven artifact

Xét một project:

~~~kotlin
group = "org.example"
version = "1.2.3"

tasks.named<Jar>("jar") {
    archiveBaseName.set("customer-api")
    archiveAppendix.set("server")
    archiveClassifier.set("demo")
}
~~~

Đây là mảnh trong project đã áp dụng Java plugin. File local có thể tên `customer-api-server-1.2.3-demo.jar`. Nhưng:

- `project.name` vẫn là tên project trong `settings.gradle.kts`.
- `group` vẫn là `org.example`.
- `project.version` vẫn là `1.2.3`.
- `archiveVersion` chỉ quyết định phần version trong tên file nếu không bị override.
- Maven `artifactId` và `version` thuộc về `MavenPublication`, không tự được suy một cách đáng tin cậy từ một filename custom.
- `archiveClassifier` có thể liên quan classifier trong Maven publication nếu artifact được publish, nhưng **không tự tạo Gradle variants/capabilities**.

**Quan trọng:** classifier `all` không tự biến JAR thường thành **fat/uber JAR**. Tên chỉ là metadata; contents mới quyết định JAR có thật sự chứa những dependency nào.

## 4. Lab Java 17 hoàn chỉnh: JAR executable và ZIP tài liệu

Ta xây một project tạo **hai files**:

~~~text
build/packages/hello-app-cli-1.2.3-demo.jar
build/distributions/hello-app-docs-1.2.3-manual.zip
~~~

JAR chứa code Java, resource và tài liệu, có `Main-Class` hợp lệ để chạy bằng JDK 17. ZIP chỉ chứa các file tài liệu. Không có Java runtime libraries bên ngoài nên `java -jar` chạy mà không cần giải quyết transitive dependencies.

### 4.1. Cấu trúc thư mục

~~~text
hello-archive/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── src/main/java/example/Main.java
├── src/main/resources/config/banner.txt
├── docs/README.md
└── legal/NOTICE.txt
~~~

Yêu cầu: một Gradle Wrapper có sẵn, JDK 17 được cài hoặc có Java toolchain resolver phù hợp. Đây là project demo không cần Maven dependencies bên ngoài.

`settings.gradle.kts`:

~~~kotlin
rootProject.name = "hello-archive"
~~~

### 4.2. Java code: `src/main/java/example/Main.java`

~~~java
package example;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws Exception {
        System.out.println("ARCHIVE_OK");

        try (InputStream in =
                 Main.class.getResourceAsStream("/config/banner.txt")) {
            if (in == null) {
                throw new IllegalStateException("Missing banner resource");
            }

            String message = new String(
                in.readAllBytes(),
                StandardCharsets.UTF_8
            ).trim();

            System.out.println("MESSAGE=" + message);
            System.out.println("ARG_COUNT=" + args.length);
        }
    }
}
~~~

`InputStream.readAllBytes()` và `StandardCharsets.UTF_8` hợp lệ trên JDK 17. Resource được đọc từ classpath **bên trong JAR**, không phụ thuộc current working directory.

### 4.3. File resource

`src/main/resources/config/banner.txt`:

~~~text
Hello from resources
~~~

Java gọi `trim()` nên việc file có newline cuối hay không không thay kết quả.

### 4.4. Tài liệu

`docs/README.md`:

~~~markdown
# Hello Archive

A small Java 17 application packaged as a runnable JAR.

The documentation ZIP contains this guide and a NOTICE file.
~~~

`legal/NOTICE.txt`:

~~~text
Educational archive packaging demonstration.

No third-party Java runtime libraries are included in this sample.
~~~

NOTICE này chỉ dùng trong **bài học**, không phải thay thế giấy phép hoặc provenance của một bản phát hành sản phẩm thật.

### 4.5. Toàn bộ `build.gradle.kts`

~~~kotlin
plugins {
    java
}

group = "org.example"
version = "1.2.3"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.named<Jar>("jar") {
    archiveBaseName.set("hello-app")
    archiveAppendix.set("cli")
    archiveVersion.set(project.version.toString())
    archiveClassifier.set("demo")
    archiveExtension.set("jar")

    destinationDirectory.set(
        layout.buildDirectory.dir("packages")
    )

    manifest {
        attributes(
            "Main-Class" to "example.Main",
            "Implementation-Title" to "Hello Archive",
            "Implementation-Version" to project.version.toString()
        )
    }

    // Java plugin đã đóng classes + main resources vào jar.
    // Chỉ bổ sung những file không thuộc sourceSet output.
    from("legal") {
        include("NOTICE.txt")
        into("META-INF")
    }

    from("docs") {
        include("README.md")
        into("docs")
    }

    exclude("**/*.bak")
    duplicatesStrategy = DuplicatesStrategy.FAIL

    isReproducibleFileOrder = true
    isPreserveFileTimestamps = false
}

val docsZip by tasks.registering(Zip::class) {
    archiveBaseName.set("hello-app")
    archiveAppendix.set("docs")
    archiveVersion.set(project.version.toString())
    archiveClassifier.set("manual")
    archiveExtension.set("zip")

    destinationDirectory.set(
        layout.buildDirectory.dir("distributions")
    )

    from("docs") {
        include("**/*.md")
        into("docs")
    }

    from("legal") {
        include("NOTICE.txt")
        into("legal")
    }

    duplicatesStrategy = DuplicatesStrategy.FAIL
    isReproducibleFileOrder = true
    isPreserveFileTimestamps = false
}

tasks.named("assemble") {
    dependsOn(docsZip)
}
~~~

Đây là **toàn bộ build script** cho lab:

1. `java` tạo task `jar` và lifecycle `assemble`.
2. `tasks.named<Jar>("jar")` cấu hình task JAR do Java plugin tạo, không tạo JAR task trùng tên.
3. `archiveBaseName` = `hello-app`, appendix = `cli`, version = `1.2.3`, classifier = `demo`, extension = `jar` tạo filename theo quy tắc.
4. `destinationDirectory` đặt JAR trong `build/packages`, không còn ở `build/libs` theo default.
5. `manifest.attributes("Main-Class" to "example.Main")` cho `java -jar` biết entry point.
6. Java plugin tự gắn `sourceSets.main.output` vào JAR: code `Main.class` và resource `banner.txt` được đóng gói.
7. Hai `from` bổ sung NOTICE và README vào các directory entries riêng của JAR.
8. `docsZip` tạo ZIP tài liệu tên `hello-app-docs-1.2.3-manual.zip`.
9. `assemble.dependsOn(docsZip)` khiến lệnh assemble tạo thêm custom ZIP; Zip task không tự tham gia assemble nếu không được nối.
10. `DuplicatesStrategy.FAIL` báo lỗi thay vì lặng lẽ bỏ qua entries có cùng destination path.
11. `isReproducibleFileOrder` và `isPreserveFileTimestamps` hỗ trợ tính tái lập trên nhiều Gradle versions.

### 4.6. Chạy Gradle và Java

Linux/macOS:

~~~bash
./gradlew --version
./gradlew clean assemble

jar --list --file build/packages/hello-app-cli-1.2.3-demo.jar

java -jar build/packages/hello-app-cli-1.2.3-demo.jar alpha beta

jar --list --file build/distributions/hello-app-docs-1.2.3-manual.zip
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean assemble
jar --list --file build/packages/hello-app-cli-1.2.3-demo.jar
java -jar build/packages/hello-app-cli-1.2.3-demo.jar alpha beta
jar --list --file build/distributions/hello-app-docs-1.2.3-manual.zip
~~~

**Stdout của `Main.main`, chính xác ba dòng:**

~~~text
ARCHIVE_OK
MESSAGE=Hello from resources
ARG_COUNT=2
~~~

Danh sách JAR entries cần chứa ít nhất:

~~~text
META-INF/MANIFEST.MF
META-INF/NOTICE.txt
example/Main.class
config/banner.txt
docs/README.md
~~~

Và ZIP tài liệu cần có:

~~~text
docs/README.md
legal/NOTICE.txt
~~~

`jar --list` có thể hiển thị thêm directory entries, và thứ tự in không phải hợp đồng cần hard-code trong test. Mã Java thực thi được vì `example.Main` có main method, `Main-Class` đúng, và chương trình không dùng external runtime JARs.

### 4.7. Biên dịch Java trực tiếp để tách lỗi source khỏi lỗi Gradle

Nếu muốn kiểm tra Java source trước khi xét packaging, Linux/macOS:

~~~bash
mkdir -p build/manual-classes/config
javac -encoding UTF-8 -d build/manual-classes src/main/java/example/Main.java
cp src/main/resources/config/banner.txt build/manual-classes/config/banner.txt
java -cp build/manual-classes example.Main alpha beta
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/manual-classes/config | Out-Null
javac -encoding UTF-8 -d build/manual-classes src/main/java/example/Main.java
Copy-Item src/main/resources/config/banner.txt build/manual-classes/config/banner.txt
java -cp build/manual-classes example.Main alpha beta
~~~

Cả hai chạy Java main với stdout như trên. Nhưng bài test `javac/java -cp` chỉ chứng minh **code/resource classpath**, chưa chứng minh tên archive hay manifest. Muốn xác nhận chúng cần chạy `./gradlew assemble`, `jar --list` và `java -jar`.

## 5. `archiveFileName` ghi đè toàn bộ tên mặc định

Mặc định:

~~~kotlin
tasks.named<Jar>("jar") {
    archiveBaseName.set("hello-app")
    archiveVersion.set("1.2.3")
    archiveClassifier.set("demo")
}
~~~

cho file kiểu `hello-app-1.2.3-demo.jar` (với appendix rỗng). Nhưng nếu viết:

~~~kotlin
tasks.named<Jar>("jar") {
    archiveFileName.set("app.jar")
}
~~~

tên đầy đủ là `app.jar` cho dù `archiveBaseName`, `archiveVersion` và `archiveClassifier` có giá trị khác. `destinationDirectory` vẫn xác định thư mục ngoài archive.

Đây là **phương án thay thế naming**, không thêm vào lab nếu còn muốn filenames trong mục 4.

### Khi nào nên dùng filename cố định?

Có thể hữu ích cho container image/Dockerfile luôn copy `app.jar`. Nhưng cần nhớ:

- Thay `project.version` không khiến filename `app.jar` tự đổi.
- Hai release cùng ghi một thư mục có thể overwrite nhau.
- CI artifact retention có thể mất thông tin version nếu không lưu metadata ngoài.
- Script mong chờ `*-1.2.3.jar` sẽ không tìm thấy.
- Maven identity/POM có thể vẫn dùng version khác.

Không chỉ đổi đuôi `.jar` thành `.zip` để giả định package đã trở thành distribution phù hợp; loại task và contents vẫn phải đúng.

## 6. `archiveVersion` khác `project.version` và manifest version

Ba nơi có thể cùng version nhưng không liên kết tự động theo hai chiều:

~~~kotlin
group = "org.example"
version = "2.0.0"

tasks.named<Jar>("jar") {
    archiveVersion.set(project.version.toString())

    manifest {
        attributes(
            "Implementation-Version" to project.version.toString()
        )
    }
}
~~~

- `project.version` là version của project và convention của nhiều plugins/publications.
- `archiveVersion` là thành phần version của **filename**.
- `Implementation-Version` là một **manifest attribute** nằm trong JAR.
- `MavenPublication.version` là version của artifact khi publish, có thể cấu hình riêng.

Nếu ai đó viết `archiveVersion.set("release")` nhưng `project.version` vẫn `2.0.0`, filename có `release` còn publication có thể là `2.0.0`. Tình trạng này không luôn sai nhưng rất dễ gây hiểu nhầm nếu version không được tài liệu hóa.

Một cách tập trung version:

~~~properties
version=1.2.3
group=org.example
~~~

trong `gradle.properties`, rồi các archive tasks dùng `project.version.toString()`. Không hard-code version khác ở nhiều build scripts nếu không có lý do rõ.

### `SNAPSHOT`, commit hash và dynamic naming

Tên `hello-app-1.2.3-SNAPSHOT.jar` chỉ chứa một chuỗi version; nó không tự cấu hình snapshot repository, Git commit hay source provenance. Nếu cần commit hash, tạo quy trình metadata rõ ràng và tránh nhúng thời gian/username tùy tiện gây mất reproducibility.

## 7. `archiveClassifier`: tên artifact không quyết định contents

Classifier phổ biến:

| Classifier | Công dụng dự kiến | Điều bắt buộc để đúng |
| --- | --- | --- |
| `sources` | JAR chứa Java source. | Task thực sự đóng `.java` files. |
| `javadoc` | JAR chứa HTML Javadoc. | Task tạo docs và đưa output vào archive. |
| `tests` | Test-classes artifact. | Có test output/classpath đúng. |
| `linux`/`windows` | Bản dành cho OS tương ứng. | Script/binary phù hợp OS. |
| `all` | Thường được đặt cho fat JAR. | Task/plugin thực sự gom runtime deps. |
| `demo` | Artifact minh họa. | Không làm thay đổi content tự động. |

Phản ví dụ:

~~~kotlin
tasks.named<Jar>("jar") {
    archiveClassifier.set("all")
}
~~~

Đặt tên vậy **không** đưa mọi dependencies từ `runtimeClasspath` vào archive. JAR thường của Java plugin chứa compiled classes/resources của project, không phải shaded bundle. Nếu cần fat JAR, dùng plugin phù hợp (chẳng hạn Shadow) và hiểu merge rules, license, service descriptors và cấu hình classpath.

### Sources và Javadoc JAR

Với Java Library plugin:

~~~kotlin
plugins {
    `java-library`
}

java {
    withSourcesJar()
    withJavadocJar()
}
~~~

Gradle tạo/đăng ký source và Javadoc artifacts với classifier theo convention. Không tự đăng ký thêm `sourcesJar` nếu plugin đã tạo task cùng tên.

Nếu cần chỉnh base name của source JAR:

~~~kotlin
tasks.named<Jar>("sourcesJar") {
    archiveBaseName.set("hello-library")
}
~~~

Đây là **mảnh bổ sung** chỉ dùng sau `withSourcesJar()`. Đổi classifier/name không biến compiled class JAR thành source JAR nếu sources chưa được `from(...)` đúng.

### Classifier và Maven consumer

Classifier là một phần của artifact metadata khi publish nhưng không phải Gradle **capability** hay **variant attributes**. Nếu muốn consumer chọn một tính năng tùy chọn cùng dependency graph/variants riêng, cần mô hình hóa feature variant thay vì chỉ tạo một file `-feature.jar`.

Nếu bạn đang publish **main library JAR**, cẩn thận khi đổi `archiveClassifier` của chính `jar` task: Maven consumers thường mong artifact main không có classifier. Có thể giữ main JAR mặc định và tạo task JAR bổ sung với classifier `docs`/`tests`/`all` phù hợp.

## 8. `destinationDirectory` đặt file ở đâu, `into` đặt file bên trong ở đâu?

Ví dụ:

~~~kotlin
tasks.named<Jar>("jar") {
    destinationDirectory.set(
        layout.buildDirectory.dir("release")
    )
}
~~~

chỉ thay **thư mục output ngoài** thành `build/release`; nó không tạo `release/` bên trong JAR.

Trái lại:

~~~kotlin
tasks.register<Zip>("docsBundle") {
    from("docs") {
        into("documentation")
    }
}
~~~

làm file `docs/README.md` có entry path `documentation/README.md` trong ZIP, nhưng không chỉ định nơi ZIP được lưu trên đĩa.

### `archiveFile` là Provider của output thật

Thay vì đoán `build/libs/foo.jar`, hãy để một task khác tham chiếu output:

~~~kotlin
val binaryJar = tasks.named<Jar>("jar")

tasks.register<Copy>("stageJar") {
    from(binaryJar.flatMap { it.archiveFile })
    into(layout.buildDirectory.dir("staging"))
}
~~~

Đây là **mảnh build script** cần project đã apply Java plugin. `archiveFile` là `Provider<RegularFile>`, phản ánh cả `destinationDirectory` lẫn `archiveFileName`. Việc nối task output provider giúp Gradle biết producer và tránh phụ thuộc vào chuỗi path cũ khi tên hoặc version đổi.

Phản ví dụ:

~~~kotlin
tasks.register<Copy>("stageJarBad") {
    from("build/libs/hello-app-1.2.3.jar")
    into(layout.buildDirectory.dir("staging"))
}
~~~

Nếu JAR chuyển sang `build/packages` hoặc thêm classifier, path cứng có thể sai; chuỗi path thuần cũng không tự mang producer task dependency đầy đủ.

### Không gọi `get()` quá sớm

`archiveFileName.get()` chỉ trả filename; `archiveFile.get().asFile` trả file path. Nhưng với task wiring, giữ Providers càng lâu càng tốt để Gradle theo dõi dependencies/lazy configuration. Tránh đọc path tại configuration rồi biến nó thành string ở nhiều subprojects.

## 9. Quyết định contents bằng `CopySpec`: `from`, `into`, `include`, `exclude`

Các archive tasks có **CopySpec**. Chúng quyết định file nào được sao chép vào archive và đường dẫn entry.

~~~kotlin
tasks.register<Zip>("releaseBundle") {
    archiveBaseName.set("my-package")
    archiveVersion.set("1.0")

    from("docs") {
        include("**/*.md")
        into("documentation")
    }

    from("config") {
        include("*.properties")
        into("config")
    }

    exclude("**/*.tmp")
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
~~~

Đây là **mảnh cấu hình**, giả định các thư mục docs/config tồn tại. Nếu có `docs/guide/start.md`, entry sẽ là `documentation/guide/start.md`. Nếu có `config/app.properties`, entry là `config/app.properties`.

### Phân biệt bốn thao tác

- `from("docs")`: nguồn trên filesystem/project.
- `into("documentation")` nằm trong nested `from`: entry path **bên trong archive**.
- `include("**/*.md")`: chỉ nhận file match pattern.
- `exclude("**/*.tmp")`: loại file match pattern.

Patterns thường được tính tương đối với source/copy spec tương ứng. `**` match nhiều cấp directory. Với cấu trúc phức tạp, kiểm tra archive entries thật bằng JDK `jar --list` trước khi publish; đừng đoán pattern hoạt động như regex tùy ý.

### Thêm nhiều `from` không có nghĩa chúng ở các archive khác nhau

~~~kotlin
from("docs") {
    into("docs")
}
from("legal") {
    into("legal")
}
~~~

Trong **cùng archive task**, cả hai nguồn nằm trong **một archive** với hai subtree. Để tạo hai files ZIP khác nhau, phải có hai archive tasks hoặc cấu hình distribution riêng.

### `eachFile` và `filesMatching`

Gradle có APIs xử lý từng entry nếu muốn đổi path/permissions hoặc transformation đặc thù. Với requirement chỉ sắp xếp thư mục, ưu tiên `from {... into(...) }` vì dễ hiểu hơn việc đổi path mọi file trong callback. Cẩn thận khi logic đó đọc thời gian, môi trường hoặc file ngoài inputs vì có thể phá reproducibility và cacheability.

## 10. Trùng tên entry và `DuplicatesStrategy`

Hai nguồn có thể cùng chứa `README.md` và đều được đóng vào `docs/README.md`. Trong ZIP/JAR, duplicate entry có thể gây lỗi hoặc tồn tại song song tùy strategy.

| Strategy | Hành vi |
| --- | --- |
| `DuplicatesStrategy.FAIL` | Throw lỗi nếu nhiều file cùng destination path. |
| `DuplicatesStrategy.EXCLUDE` | Giữ item đầu, bỏ item đến sau. |
| `DuplicatesStrategy.INCLUDE` | Không chặn duplicate; có thể có nhiều entries giống tên. |
| `DuplicatesStrategy.WARN` | Cảnh báo nhưng không bỏ duplicate. |
| `DuplicatesStrategy.INHERIT` | Lấy strategy từ parent CopySpec; nested specs thường dùng. |

Trong release pipeline, **FAIL** thường là điểm bắt đầu an toàn vì làm lỗi rõ ràng. Dùng EXCLUDE để “làm build xanh” khi chưa biết file nào đúng có thể âm thầm bỏ resources.

Đặc biệt với fat JAR, `META-INF/services/*` cần merge đúng format; chọn EXCLUDE bừa có thể làm mất provider. Các thư viện có `LICENSE` hoặc `NOTICE` khác nhau cũng không nên bị âm thầm ghi đè.

Trong lab đã cấu hình:

~~~kotlin
duplicatesStrategy = DuplicatesStrategy.FAIL
~~~

Điều này có thể giúp tìm vấn đề ngay khi build. Nếu có xung đột, xem input paths và layout chứ không sửa mặc định thành INCLUDE ngay.

## 11. `Jar`, Java source set và manifest

Java plugin tạo `jar` với production **`sourceSets.main.output`**. Điều này thường gồm:

~~~text
src/main/java/*.java
    -> compileJava
    -> build/classes/java/main/**/*.class
    -> JAR entries

src/main/resources/**
    -> processResources
    -> build/resources/main/**
    -> JAR entries
~~~

Bạn không cần viết `from("src/main/java")` trong `jar` để có classes; làm thế có thể vô tình đóng nguyên Java source files vào binary JAR thay vì compiled classes.

### Manifest cho executable JAR

~~~kotlin
tasks.named<Jar>("jar") {
    manifest {
        attributes(
            "Main-Class" to "example.Main",
            "Implementation-Version" to project.version.toString()
        )
    }
}
~~~

Đây là mảnh khi `example.Main` có `public static void main(String[] args)`. `Main-Class` là tên Java **fully qualified class**, không phải `example/Main.class` hoặc `Main.java`.

Nếu JAR chứa external dependencies:
- `Main-Class` không tự thêm chúng vào runtime classpath.
- `java -jar` có thể báo `NoClassDefFoundError` nếu thiếu thư viện khác.
- Dùng Application distributions, explicit `Class-Path` manifest với layout đúng, hoặc fat JAR plugin nếu requirement thực sự cần single JAR.
- Đừng giải quyết bằng `archiveClassifier.set("all")` đơn thuần.

### Manifest version khác publication version

`Implementation-Version` nằm trong `META-INF/MANIFEST.MF`. Nó không tự thay `project.version`/POM/Gradle Module Metadata. Nếu muốn đồng bộ, dùng cùng nguồn version khi build script tạo manifest.

### Source JAR và binary JAR

- `jar`: compiled classes/resources.
- `sourcesJar`: source files.
- `javadocJar`: generated HTML docs.
- `archiveClassifier` chỉ góp phần vào filename/metadata, không tự thay nguồn content.

## 12. `Zip`, `Tar`, compression và extension

Một ZIP task:

~~~kotlin
tasks.register<Zip>("releaseDocs") {
    archiveBaseName.set("sample")
    archiveVersion.set("1.0")
    archiveClassifier.set("docs")
    destinationDirectory.set(
        layout.buildDirectory.dir("distributions")
    )

    from("docs") {
        into("docs")
    }
}
~~~

Nếu `docs` tồn tại, nó tạo ZIP với contents từ thư mục đó. Classifier `docs` phân biệt filename, không phải lệnh “đóng gói docs” tự động.

Một TAR.GZ task:

~~~kotlin
tasks.register<Tar>("releaseTarGz") {
    archiveBaseName.set("sample")
    archiveVersion.set("1.0")
    archiveClassifier.set("linux")

    compression = org.gradle.api.tasks.bundling.Compression.GZIP
    archiveExtension.set("tar.gz")

    destinationDirectory.set(
        layout.buildDirectory.dir("distributions")
    )

    from("scripts") {
        into("bin")
    }
}
~~~

Đây là **mảnh ví dụ**, giả định `scripts` có files. File kết quả theo naming là `sample-1.0-linux.tar.gz`. Đặt `archiveExtension.set("tar.gz")` trên task `Zip` **không biến** dữ liệu ZIP thành TAR.GZ; phải chọn `Tar` và `compression` đúng.

### JAR có phải ZIP?

JAR dùng cấu trúc ZIP nhưng có Java manifest/classpath conventions. Không được suy rằng chỉ đổi tên ZIP thành JAR là JVM hiểu đó là executable Java package. Phải có class files và manifest đúng.

### Quyền file và OS

Nếu TAR chứa shell scripts, cần xét permissions/executable bits và hệ điều hành đích. Gradle 9 dùng reproducible permissions defaults; tuy nhiên muốn script executable có thể cần cấu hình file permissions thích hợp. Kiểm tra file thật sau khi extract trên target OS, không chỉ nhìn classifier `linux`.

## 13. Reproducible archives: ordering và timestamps

Một build tốt nên có thể tạo cùng archive bytes từ cùng inputs/toolchains. Nhưng metadata trong archive có thể khác nhau vì:
- Thứ tự duyệt files của filesystem.
- Entry timestamps.
- File/dir permissions.
- Manifest chứa build timestamp, hostname hoặc username.
- Generated files có UUID/thời gian hiện tại.
- JDK/compiler/plugin/dependency versions khác nhau.

**Gradle 9+** theo tài liệu hiện hành tạo archives dựa trên `AbstractArchiveTask` với mặc định reproducible file order, timestamps và permissions. **Gradle trước 9** có thể có defaults khác; không lấy hướng dẫn mới nhất làm bằng chứng cho Wrapper cũ.

Một cấu hình tường minh tương thích nhiều bản:

~~~kotlin
tasks.withType<AbstractArchiveTask>().configureEach {
    isReproducibleFileOrder = true
    isPreserveFileTimestamps = false
}
~~~

Điều này giảm sự phụ thuộc vào file order/timestamps của source filesystem. **Nó không bảo đảm** SHA-256 giống nhau nếu generated content, compiler, manifest hay artifact dependencies vẫn khác.

### Kiểm tra checksum thực

Linux/macOS:

~~~bash
sha256sum build/packages/hello-app-cli-1.2.3-demo.jar
~~~

PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 build/packages/hello-app-cli-1.2.3-demo.jar
~~~

Hash cụ thể phải được **tính từ bytes thật**. Không ghi một hash cố định trong hướng dẫn rồi gọi đó là kết quả. Để kiểm thử reproducibility, build clean hai lần từ source giống hệt trong môi trường được kiểm soát và so sánh SHA-256.

### Timestamps/permissions nâng cao

Gradle mới còn có các APIs như `reproducibleFileTimestamp` và cấu hình file permissions. Nếu dùng, xác minh Gradle Wrapper hỗ trợ API đó, giới hạn timestamp của ZIP/TAR và quan hệ với `isPreserveFileTimestamps`. Không cố dùng API mới trên Gradle cũ chỉ vì code trong tài liệu hiện hành biên dịch ở Gradle 9.

## 14. Files generated bởi task khác phải có producer dependency

Nếu một archive cần `build/generated/notes/RELEASE.txt`, chỉ thêm `from("build/generated/notes")` có thể không bảo đảm task tạo notes chạy trước archive.

Ví dụ mảnh build script:

~~~kotlin
val generateNotes by tasks.registering {
    val output =
        layout.buildDirectory.file("generated/notes/RELEASE.txt")

    outputs.file(output)

    doLast {
        val target = output.get().asFile
        target.parentFile.mkdirs()
        target.writeText("Release notes for sample", Charsets.UTF_8)
    }
}

val releaseBundle by tasks.registering(Zip::class) {
    archiveBaseName.set("sample")
    archiveVersion.set("1.0")

    // Producer phải chạy trước khi archive đọc output.
    dependsOn(generateNotes)

    from(layout.buildDirectory.dir("generated/notes")) {
        into("notes")
    }
}
~~~

Đây là **mảnh minh họa các tasks**, không cần nhúng vào lab chính. Khi `releaseBundle` chạy, Gradle schedule `generateNotes` trước; file thành `notes/RELEASE.txt` trong ZIP.

Với production custom task types, dùng `@Input`, `@OutputFile`, `RegularFileProperty` và TaskProvider wiring để tối ưu caching/Configuration Cache. `afterEvaluate` không thay thế task dependency: hoãn configuration không làm file được tạo trước execution.

### Provider-based wiring

Khi archive nguồn từ task output, dùng `TaskProvider.flatMap` hoặc API nhận TaskProvider để giữ task relationship. Tránh gọi `tasks.getByName(...)` tại configuration time chỉ để lôi ra file path, vì có thể eager-configure tasks và làm build khó tối ưu.

## 15. Archive tasks nào chạy với `assemble`/`build`?

Java plugin gắn task `jar` vào lifecycle `assemble`. Plugin Base/Java tạo các lifecycle tasks như `assemble`, `check`, `build`, nhưng **custom ZIP task không tự động tham gia `assemble` chỉ vì kiểu Zip**.

Mẫu đúng:

~~~kotlin
val docsBundle by tasks.registering(Zip::class) {
    from("docs")
}

tasks.named("assemble") {
    dependsOn(docsBundle)
}
~~~

Điều này là mảnh bổ sung trong project có Base/Java plugin. Khi `./gradlew assemble`, Gradle thêm `docsBundle` vào task graph.

Ngược lại:

~~~kotlin
tasks.register<Zip>("docsBundle") {
    from("docs")
}
~~~

chỉ đăng ký task. Không dán **cả hai ví dụ** vào một file vì sẽ trùng tên task. Để chạy riêng custom archive, gọi `./gradlew docsBundle`.

### Multi-project

Mỗi subproject có tên, version và `layout.buildDirectory` riêng. Nếu bạn gộp tất cả outputs vào một thư mục shared với cùng filename, tasks có thể overwrite nhau hoặc Gradle báo overlapping outputs. Dùng tên module/version/classifier riêng hoặc giữ outputs theo subproject.

## 16. Maven Publish: tên file local không đồng nghĩa tọa độ public

Nếu một Java library publish lên Maven repository, nên dùng Maven Publish plugin và một Java component có metadata rõ:

~~~kotlin
plugins {
    `java-library`
    `maven-publish`
}

group = "org.example"
version = "1.2.3"

java {
    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
            artifactId = "hello-library"
        }
    }
}
~~~

Đây là **project/library publishing mẫu riêng**, không dán trực tiếp vào lab mục 4 đang đổi classifier của main `jar` thành `demo`. Publication có danh tính `org.example:hello-library:1.2.3`, khác với việc chỉ đổi tên file local.

### Custom docs ZIP artifact

Khi `mavenJava` publication và `docsZip` task đã tồn tại, có thể thêm:

~~~kotlin
publishing {
    publications {
        named<MavenPublication>("mavenJava") {
            artifact(tasks.named<Zip>("docsZip")) {
                classifier = "docs"
                extension = "zip"
            }
        }
    }
}
~~~

Đây là **mảnh cấu hình**, không tự tạo `docsZip` hoặc `mavenJava`. Task archive được đưa vào artifact publication; Gradle có thể lấy extension/classifier từ task, nhưng ví dụ đặt tường minh.

Những điểm cần kiểm tra:

- Main JAR không bị thêm classifier ngoài ý muốn nếu consumer mong unclassified artifact.
- Artifacts trong một publication có identity phân biệt, thường qua classifier + extension.
- Supplementary ZIP không tự định nghĩa Gradle feature variant/capability và dependency graph.
- `artifactId`/`version` của publication có thể khác `archiveBaseName`/`archiveVersion`; đừng suy từ filename.
- `publish` không tự upload mọi Zip tasks trong project nếu bạn không cấu hình publication/artifact.
- Nếu chỉ cần upload ZIP lên CI artifact store, không nhất thiết biến nó thành Maven artifact.

Với publication đã định nghĩa:

~~~bash
./gradlew generatePomFileForMavenJavaPublication
./gradlew generateMetadataFileForMavenJavaPublication
./gradlew publishToMavenLocal
~~~

Lệnh chỉ khả dụng khi `maven-publish` và publication đúng tên tồn tại. Hãy kiểm tra POM, Gradle Module Metadata và artifacts thực bằng một consumer độc lập trước release.

## 17. Đừng đóng gói cả project root và làm rò secrets

Phản ví dụ:

~~~kotlin
tasks.register<Zip>("unsafeBundle") {
    from(".")
}
~~~

Việc copy nguyên project root có thể đưa `.env`, private keys, Gradle caches, logs, IDE configs, test reports và build artifacts nhạy cảm vào ZIP.

An toàn hơn:

~~~kotlin
tasks.register<Zip>("safeDocs") {
    from("docs") {
        include("**/*.md")
        exclude("**/internal/**")
    }

    from("legal") {
        include("NOTICE.txt")
    }
}
~~~

Cần **whitelist inputs** và kiểm tra archive contents trước khi publish. Không thể coi file bị Git ignore là tự động bị Gradle exclude. Khi tạo archive từ những file không tin cậy, cần tránh entry paths chứa parent traversal, kiểm tra path khi giải nén để chống Zip Slip.

Một bản phát hành thật cần NOTICE/LICENSE chính xác cho bản quyền và dependencies, không dùng sample NOTICE để che license/provenance thật.

## 18. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| Tên JAR không đổi sau khi sửa version | `archiveFileName` đã override. | Bỏ override hoặc thiết kế filename policy khác. |
| JAR có version 1.1 nhưng POM version 1.2 | `archiveVersion` khác `project.version`/publication version. | Thống nhất version source. |
| `jar` vẫn ở `build/libs` | Chưa cấu hình `destinationDirectory` đúng task. | Dùng `tasks.named<Jar>("jar")` và `layout.buildDirectory.dir(...)`. |
| `java -jar` báo no main manifest attribute | Thiếu `Main-Class`. | Đặt manifest attribute với FQCN đúng. |
| `java -jar` báo `NoClassDefFoundError` | Thiếu external runtime dependencies. | Dùng distribution/classpath/fat JAR có nội dung thật. |
| `-all.jar` vẫn không có dependency classes | `archiveClassifier` chỉ đổi tên. | Thiết kế fat JAR task/plugin đúng. |
| ZIP không chứa file docs | `from` path sai hoặc include pattern không match. | Kiểm tra source path và `jar --list`. |
| Resource đọc bằng `getResourceAsStream` ra null | Resource không có trong JAR hoặc sai path. | Kiểm tra `src/main/resources`, includes, archive entries. |
| File xuất hiện sai thư mục trong ZIP | `into` đặt sai copy spec. | Sửa nested `from { into(...) }`. |
| Duplicate entry fail | `DuplicatesStrategy.FAIL` tìm thấy collision. | Xem sources, sửa destination paths hoặc merge rõ ràng. |
| `stageJar` dùng path cũ sau rename | Hard-code file path. | Dùng `jarTask.flatMap { it.archiveFile }`. |
| Custom ZIP không chạy trong `assemble` | Chưa nối lifecycle. | `assemble.dependsOn(docsBundle)`. |
| Hai subprojects ghi đè cùng file | Tên và directory output trùng nhau. | Phân biệt theo project/version/classifier. |
| Checksum khác giữa hai máy | Timestamps/order/compiler/generated content khác. | Bật reproducible flags, pin inputs/toolchains. |
| TAR.GZ giải nén lỗi | Đổi extension nhưng chưa dùng `Tar` + GZIP. | Sử dụng task type/compression thật. |
| Maven consumer không thấy artifact | ArtifactId/classifier/publication sai. | Xem `MavenPublication`, POM, artifacts. |
| JAR có nguồn Java nhưng không có class | `from("src/main/java")` thay vì compiled output. | Dùng Java plugin `jar` + sourceSets output. |
| Archive chứa file bí mật | `from(".")` quá rộng. | Whitelist sources và scan artifact. |

## 19. Checklist phát hành

- [ ] Dùng đúng task `Jar`/`Zip`/`Tar` cho định dạng mong muốn.
- [ ] Tên file phản ánh base, appendix, version, classifier, extension đúng policy.
- [ ] Không override `archiveFileName` nếu muốn tên tự thay đổi theo version.
- [ ] `destinationDirectory` chính xác và không collision với output khác.
- [ ] `project.version`, `archiveVersion`, manifest và publication version thống nhất khi cần.
- [ ] Nội dung archive chỉ gồm files cần thiết; không vô tình chứa secrets.
- [ ] `from`/`into`/`include`/`exclude` được kiểm tra bằng archive listing thực.
- [ ] Duplicate entries được xử lý bằng policy có chủ đích.
- [ ] Runnable JAR có `Main-Class` và đủ runtime classpath.
- [ ] Class files/resources đúng; không nhầm source JAR với binary JAR.
- [ ] Dùng `archiveFile` Provider cho task tiêu thụ output.
- [ ] Inputs generated có task dependency/output provider đúng.
- [ ] Reproducible ordering/timestamps/permissions được kiểm soát theo Gradle version.
- [ ] Custom archive nối vào `assemble` nếu lifecycle cần.
- [ ] Publication có main artifact và classifier artifacts đúng.
- [ ] Chạy `jar --list`, `java -jar` và checksum/tests trước release.
- [ ] CI không dùng hard-coded tên/filepath dễ sai sau đổi version.

## 20. Câu hỏi tự kiểm tra

1. **Gradle đặt tên archive như thế nào?** Theo `base-appendix-version-classifier.extension`, bỏ phần không có.
2. **Tên task có tự quyết định filename không?** Không.
3. **`archiveClassifier.set("all")` có tạo fat JAR không?** Không; chỉ là tên/metadata.
4. **`archiveFileName.set("app.jar")` có còn tự đổi theo version không?** Không, vì tên đã explicit.
5. **`destinationDirectory` và `into` khác gì?** Thư mục ngoài archive vs directory entries bên trong.
6. **`archiveFile` trả gì?** Provider cho output file thực tế.
7. **`archiveVersion` có tự đổi `project.version` không?** Không.
8. **`Implementation-Version` trong manifest có tự đổi Maven POM không?** Không.
9. **Muốn `java -jar` chạy được cần gì?** Compiled main class, `Main-Class`, runtime deps đầy đủ.
10. **JAR chuẩn có tự gồm tất cả external libraries không?** Không.
11. **Đổi classifier thành `sources` có biến binary JAR thành source JAR không?** Không.
12. **`from("docs") { into("help") }` tạo entry nào cho README?** `help/README.md`.
13. **`DuplicatesStrategy.FAIL` có lợi ích gì?** Ngăn lặng lẽ tạo duplicate paths.
14. **Gradle 9 mặc định reproducible archive ordering/timestamps không?** Có theo tài liệu hiện hành; với bản cũ cần xem defaults.
15. **Đổi extension của Zip sang `tar.gz` có tạo TAR.GZ không?** Không; dùng `Tar` + `Compression.GZIP`.
16. **Custom ZIP có tự chạy trong assemble không?** Không, trừ khi đã được nối.
17. **Vì sao dùng `flatMap { it.archiveFile }`?** Giữ output provider và producer relationship.
18. **Đổi `archiveBaseName` có tự đổi Maven `artifactId` không?** Không nên suy như vậy.
19. **Nếu cả `jar` và `docsZip` ở một thư mục, cần lưu ý gì?** Không trùng output filename, đúng nội dung và version.
20. **Lệnh nào kiểm tra kết quả thực?** `jar --list --file`, `java -jar`, SHA-256, publication metadata nếu publish.

## Nguồn Gradle chính thức

- [Gradle — Working With Files / Archives](https://docs.gradle.org/current/userguide/working_with_files.html): cách đặt tên archive, nội dung, CopySpec và reproducibility.
- [Gradle — AbstractArchiveTask](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.AbstractArchiveTask.html): archive properties, `archiveFileName`, `archiveFile`, `destinationDirectory`.
- [Gradle — Jar Task](https://docs.gradle.org/current/dsl/org.gradle.jvm.tasks.Jar.html): JAR content, manifest và archive naming.
- [Gradle — Zip Task](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.Zip.html): Zip archive configuration.
- [Gradle — Tar Task](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.Tar.html): TAR compression và extension.
- [Gradle — Base Plugin](https://docs.gradle.org/current/userguide/base_plugin.html): `archivesName`, default directories và `assemble`.
- [Gradle — Building Java Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): Java plugin `jar` và manifest.
- [Gradle — DuplicatesStrategy](https://docs.gradle.org/current/javadoc/org/gradle/api/file/DuplicatesStrategy.html): `FAIL`, `EXCLUDE`, `INCLUDE`, `WARN` và `INHERIT`.
- [Gradle — CopySpec API](https://docs.gradle.org/current/javadoc/org/gradle/api/file/CopySpec.html): copy source, destination, filters.
- [Gradle — Maven Publish](https://docs.gradle.org/current/userguide/publishing_maven.html): MavenPublication/artifactId/version.
- [Gradle — Custom Publishing](https://docs.gradle.org/current/userguide/publishing_customization.html): supplementary artifacts, classifier và extension.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): TaskProvider, `named`, `register`.

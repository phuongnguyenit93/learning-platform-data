# Kiểm tra artifact tạo ra trước khi phát hành trong Gradle

## 1. Vấn đề: build thành công không đồng nghĩa artifact sẵn sàng phát hành

Bạn chạy `gradle build` và thấy `BUILD SUCCESSFUL`, nhưng khi tải JAR lên repository hoặc đưa vào container, ứng dụng không khởi động. Một số nguyên nhân phổ biến:

- File được upload là `build/libs/app-old.jar` chứ không phải JAR vừa được build.
- Manifest thiếu `Main-Class` hoặc trỏ đến class sai.
- Class chính có mặt nhưng `release.properties`/template/resource quan trọng lại bị loại khỏi JAR.
- Bytecode biên dịch cho Java 21 trong khi khách hàng chỉ chạy Java 17.
- Một thư viện **thin JAR** chạy tốt bằng `gradle run` nhưng không chạy một mình bằng `java -jar` vì thiếu runtime dependencies.
- ZIP/JAR có entries trùng, file bí mật, metadata version sai, đường dẫn entry không an toàn, hoặc file đã bị thay sau khi kiểm tra.
- Maven POM, Gradle Module Metadata, sources/Javadoc artifacts, license/NOTICE hoặc chữ ký phát hành bị thiếu.
- JAR chứa timestamp hoặc dữ liệu môi trường biến động làm SHA-256 khác nhau giữa các lần build.

**Kiểm tra artifact trước khi phát hành** là kiểm tra chính **file sẽ được người dùng tải hoặc chương trình deploy sử dụng**, ở giai đoạn sau khi package và trước khi publish/deploy. Đây là một **release quality gate**, không chỉ là một loạt unit tests.

Bài thuộc chủ đề **Đóng gói** của module **Build Tool Gradle**. Trọng tâm là Java JAR, ZIP/distribution, Gradle task wiring, kiểm tra cấu trúc/nội dung/metadata, smoke test, checksum và tự động hóa chất lượng phát hành.

Sau bài học, bạn có thể:

1. Tìm artifact đúng từ `Jar.archiveFile`/task output thay vì đoán tên.
2. Liệt kê archive entries, đọc manifest và resources bằng JDK/ZIP tools.
3. Kiểm tra tên class, Java bytecode version, Java 17 runtime compatibility.
4. Phân biệt thin JAR, fat JAR, Spring Boot executable JAR, WAR và application distribution.
5. Xác minh runtime dependencies, metadata, licenses, secrets và khả năng chạy trên môi trường đích.
6. Tự viết Gradle `verifyReleaseJar` task với `@InputFile`/`@Input` và nối vào `check`.
7. Tạo project Java 17 runnable và chạy smoke test trên chính JAR.
8. Tính SHA-256, so hai clean builds, kiểm checksum trước và sau upload.
9. Kiểm tra Maven publication POM/Gradle Module Metadata và ký artifact khi chính sách yêu cầu.
10. Thiết kế CI chặn upload khi artifact không đáp ứng điều kiện.

## 2. Thế nào là một artifact hợp lệ?

Các nhóm kiểm tra độc lập nhau:

| Nhóm | Câu hỏi cần trả lời |
| --- | --- |
| **Đúng identity** | Đúng project, version, classifier, extension, commit, target platform và repository? |
| **Đúng định dạng** | JAR/ZIP/WAR/TAR có đọc được, không hỏng, không có entry paths nguy hiểm? |
| **Đủ nội dung** | Classes, resources, manifest, scripts, dependencies cần thiết đã có? |
| **Khả năng tương thích** | Bytecode, public API và dependencies phù hợp JVM/container/consumer? |
| **Hành vi thực tế** | Artifact có chạy/được consume thành công ở môi trường mục tiêu? |
| **Tính toàn vẹn** | Bytes có khớp hash đã kiểm và không đổi trong lúc upload? |
| **Tính tái lập** | Cùng input có thể tạo artifact byte-for-byte tương đương? |
| **Chính sách phát hành** | Licenses, NOTICE, SBOM, signatures, provenance, security scan có đạt? |

**Không một kiểm tra đơn lẻ thay thế toàn bộ các nhóm trên.** `jar --list` chứng minh phần nào archive đọc được nhưng không chứng minh app chạy. Một SHA-256 khớp chứng minh bytes khớp giá trị tham chiếu, không chứng minh software không có lỗ hổng.

### 2.1. Phân loại output theo plugin

| Artifact | Plugin/task | Hướng kiểm tra |
| --- | --- | --- |
| Java library JAR | `java-library`/`java` → `jar` | API classes, resources, Java target, metadata dependencies |
| Executable JAR | `application` + manifest trong `jar` | Main-Class, class, resource, smoke `java -jar` |
| Application distribution | `application` → `installDist`, `distZip` | Startup scripts, `lib/` và runtime deps |
| WAR | `war` → `war` | `WEB-INF/classes`, `WEB-INF/lib`, servlet container |
| Fat/uber JAR | Shadow hoặc plugin khác → `shadowJar` | Gộp class/resources, service files, conflicts/relocations |
| Spring Boot JAR | Spring Boot plugin → `bootJar` | `BOOT-INF/classes`, `BOOT-INF/lib`, launcher, smoke test |
| Sources/Javadoc JAR | `withSourcesJar()`, `withJavadocJar()` | Nguồn/docs, classifier và publication policy |
| Maven publication | `maven-publish` | POM, Gradle Module Metadata, coordinates và published artifact |
| Signed artifacts | Signing/CI | Signature trên đúng bytes, trusted identity/key |

Thư viện không có `Main-Class` vẫn hoàn toàn hợp lệ nếu mục đích là consumer import API. Ngược lại, JAR dự kiến chạy bằng `java -jar` mà thiếu entry point phải bị chặn.

## 3. Chọn đúng artifact từ Gradle task output

### 3.1. Tên JAR thường có version

Thông thường Java plugin tạo `jar` output dưới `build/libs`. Tên dựa trên `archiveBaseName`, `archiveVersion`, `archiveClassifier` và `archiveExtension`:

~~~text
build/libs/release-artifact-lab-1.0.0.jar
~~~

Đây là ví dụ, không phải đường cố định của mọi build. Khi team đổi version/classifier hoặc dùng `shadowJar`/`bootJar`, việc hard-code `build/libs/app.jar` dễ kiểm sai file.

Với Kotlin DSL:

~~~kotlin
val jarProducer = tasks.named<Jar>("jar")
val actualJar = jarProducer.flatMap { it.archiveFile }
~~~

`archiveFile` là `Provider<RegularFile>`, trỏ output của chính task producer. Nếu được nối vào property `@InputFile` của verification task, Gradle cũng suy ra quan hệ task dependency. Đây là cách **kiểm tra đúng output** thay vì đoán filename.

### 3.2. Chọn đúng project trong multi-project build

~~~bash
./gradlew :library:jar
./gradlew :app:distZip
./gradlew :library:tasks --all
~~~

`:library:jar` và `:app:jar` là hai outputs khác nhau. Nếu publication dùng `shadowJar` thì verify `jar` mặc định có thể **không liên quan** đến file sẽ upload. Hãy kiểm tra plugin và publication artifact thực tế.

### 3.3. Đọc task model, không đoán

Ví dụ snippet dùng để khai báo dependency đến JAR producer:

~~~kotlin
val jarTask = tasks.named<Jar>("jar")

tasks.register("explainArtifact") {
    val output = jarTask.flatMap { it.archiveFile }
    inputs.file(output)
    doLast {
        println("Archive: " + output.get().asFile.absolutePath)
    }
}
~~~

Đây là fragment, yêu cầu plugin Java tạo task `jar`. Nó chỉ in đường dẫn, không kiểm tra toàn bộ artifact. Đối với quality gate, dùng typed `VerifyReleaseJar` ở mục 10 để thực sự fail nếu archive sai.

**Lưu ý:** Provider có thể biết output path ngay từ configuration; **không chứng minh file đã tồn tại**. Phải chạy producer task hoặc nối input task dependency trước khi kiểm tra.

## 4. Kiểm tra archive bằng công cụ JDK/ZIP

### 4.1. jar --list hoặc jar tf

~~~bash
jar --list --file build/libs/release-artifact-lab-1.0.0.jar
~~~

Viết ngắn:

~~~bash
jar tf build/libs/release-artifact-lab-1.0.0.jar
~~~

Với ví dụ Java 17 ở phần sau, những entries quan trọng là:

~~~text
META-INF/MANIFEST.MF
demo/release/Main.class
release.properties
~~~

Có thể còn directory entries `META-INF/`, `demo/`... Thứ tự/định dạng output thay theo JDK/Gradle; ba entry trên là **thứ cần tìm**, không phải stdout hoàn chỉnh cố định.

### 4.2. Kiểm tra đúng đường package

Source:

~~~java
package demo.release;

public final class Main {
    public static void main(String[] args) {
        System.out.println("running");
    }
}
~~~

Class đã compile phải có dạng path:

~~~text
demo/release/Main.class
~~~

Nếu manifest viết `Main-Class: demo.release.Main` mà archive chỉ chứa `Main.class` ở root, JVM sẽ không tìm đúng class. Tên Java package khác tên Gradle project: đừng suy ra entry path từ tên JAR.

### 4.3. Đọc manifest

Với `unzip` trên Linux/macOS:

~~~bash
unzip -p build/libs/release-artifact-lab-1.0.0.jar META-INF/MANIFEST.MF
~~~

Các dòng cần xem trong bài lab:

~~~text
Manifest-Version: 1.0
Main-Class: demo.release.Main
Implementation-Title: release-artifact-lab
Implementation-Version: 1.0.0
~~~

Không nhầm `Manifest-Version: 1.0` (version của format) với release version `1.0.0`. Manifest có thể có CRLF và folding cho dòng dài, nên validator nên parse bằng `java.util.jar.Manifest` thay vì tìm chuỗi thô qua newline.

Với Windows, có thể extract **chỉ một entry** vào thư mục kiểm tra riêng:

~~~powershell
New-Item -ItemType Directory -Force inspect | Out-Null
Set-Location inspect
jar --extract --file ..\build\libs\release-artifact-lab-1.0.0.jar META-INF/MANIFEST.MF
Get-Content .\META-INF\MANIFEST.MF
Set-Location ..
~~~

Không extract archive lạ trực tiếp vào source workspace: entry names như `../path` có thể gây rủi ro ghi đè khi dùng công cụ giải nén không an toàn.

### 4.4. Đọc resource trong JAR

~~~bash
unzip -p build/libs/release-artifact-lab-1.0.0.jar release.properties
~~~

Với project lab, nội dung phải là:

~~~text
release.channel=stable
release.version=1.0.0
~~~

Nếu file bị thiếu, kiểm tra `src/main/resources`, `processResources`, `Jar.from`, `CopySpec.include/exclude` và `into`. Một class có thể compile thành công dù resource chỉ được truy cập khi chạy.

### 4.5. Kiểm tra ZIP integrity

~~~bash
unzip -t build/libs/release-artifact-lab-1.0.0.jar
~~~

Trên hệ có `unzip`, exit code 0 khi archive integrity check pass. Lệnh này khác với `jar --list`, thường phải đọc dữ liệu entries để kiểm tra CRC. Không suy luận rằng ZIP integrity pass thì class/API/runtime dependencies đã đúng.

Windows không luôn có `unzip`; ví dụ Gradle validator sau dùng Java `ZipFile` để đọc các entries cần thiết. Nếu yêu cầu integrity đầy đủ mọi entry, thêm bước đọc/CRC cho toàn bộ archive bằng tool phù hợp.

## 5. Kiểm tra bytecode và JVM mục tiêu

### 5.1. Java 17 class major version 61

JVM class files có header `CAFEBABE`, tiếp theo là minor và major version. Bảng phổ biến:

| Java | Major |
| --- | ---: |
| 8 | 52 |
| 11 | 55 |
| **17** | **61** |
| 21 | 65 |
| 25 | 69 |

Để đọc class từ một JAR:

~~~bash
javap -verbose -classpath build/libs/release-artifact-lab-1.0.0.jar demo.release.Main
~~~

Đầu ra dài; tìm:

~~~text
minor version: 0
major version: 61
~~~

Với Java 17 runtime, class major65 là không tương thích. Đừng “sửa” class header từ65 xuống61 bằng trình hex editor: bytecode/constant pool/API có thể dùng tính năng runtime cũ không hiểu.

### 5.2. Java toolchain và --release

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Toolchain chọn JDK compiler thích hợp; `--release 17` kiểm soát Java language/API target và tạo bytecode tương thích Java 17. Khác với JVM chạy Gradle daemon. Nếu project phụ thuộc một third-party library chứa class major65, chỉ đặt `options.release=17` cho project source **không** tự làm dependency tương thích.

### 5.3. Đừng chỉ kiểm tra một class ở artifact lớn

Kiểm tra main class major61 trong bài lab đủ để minh họa; với release thật:

- Xét tất cả `*.class` trong JAR.
- Xét toàn bộ runtime dependency JARs của distribution.
- Với multi-release JAR, đọc manifest `Multi-Release: true` và entries `META-INF/versions/` theo đúng runtime policy.
- Xét Kotlin/Scala/Groovy bytecode nếu build đa ngôn ngữ.
- Smoke test thực tế trên **JDK thấp nhất** mà sản phẩm cam kết hỗ trợ.
- Đừng quảng cáo `org.gradle.jvm.version=17` khi file thực tế chứa classes chỉ Java21 có thể đọc.

### 5.4. Kiểm tra public ABI của thư viện

~~~bash
javap -public -classpath build/libs/my-library-1.0.0.jar my.package.PublicApi
~~~

Đây là lệnh minh họa, phải thay class và JAR thật. Nó giúp phát hiện public methods/fields types ngoài ý định, nhưng không thay thế binary compatibility analyzer hoặc consumer compile test khi nâng version library.

## 6. Duplicate entries, resource conflicts và đường dẫn nguy hiểm

### 6.1. Vì sao phải kiểm tra duplicate entries?

Ví dụ hai nguồn cùng tạo entry:

~~~text
META-INF/services/com.example.Service
META-INF/services/com.example.Service
~~~

Một ZIP có thể chứa hai entries cùng tên. Tooling khác nhau có thể đọc entry đầu/cuối hoặc phản ứng khác nhau. Trong JAR ứng dụng, duplicate class hoặc descriptor có thể gây runtime lỗi rất khó debug.

Với một JAR do project tự đóng gói mà **không cần merge**, có thể dùng:

~~~kotlin
import org.gradle.api.file.DuplicatesStrategy

tasks.named<Jar>("jar") {
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
~~~

Đây là **mẫu chọn policy**, không phải lúc nào cũng cần với mọi plugin. Với fat JAR, file service descriptors thường phải được **merge có chủ đích**; `EXCLUDE` ngẫu nhiên có thể làm mất providers.

### 6.2. Zip slip/path traversal

Archive từ nguồn lạ có thể chứa:

~~~text
../secret.txt
/absolute/path
folder\..\outside.txt
~~~

Chỉ extract khi đã kiểm path entry, vào thư mục scratch và giới hạn quyền. Release validator nên **fail khi xuất hiện entry path không được phép**, không rename lặng lẽ. Với archive thật sự không tin cậy còn cần kiểm Windows drive names, symlinks, Unicode normalization và size/entry limits.

### 6.3. ZIP bomb, quá nhiều entries

Một archive có nén quá mạnh có thể gây quá tải khi extract. Việc list names hoặc đọc một số entries không chứng minh không có ZIP bomb. Với file bên ngoài, kiểm số entries, uncompressed sizes và resource limits; tránh extract toàn bộ khi chưa cần.

### 6.4. Class/resource không thuộc release

Liệt kê entries để tìm:

- `.env`, credential files, keystores, private keys.
- `application-dev.properties` chứa secrets.
- Test fixtures/samples nhạy cảm.
- Internal notes, absolute workspace paths, username.
- License/NOTICE files bị thiếu hoặc bị merge sai.
- Dependencies JAR nằm ngoài layout được artifact type hỗ trợ.

Không upload artifact nội bộ lên công cụ quét công khai nếu nội dung nhạy cảm; dùng CI/security tooling được tổ chức cho phép.

## 7. Thin JAR khác executable distribution

### 7.1. Java plugin thường tạo thin JAR

`jar` của plugin Java đóng compiled classes/resources của project, **không tự chèn** mọi dependency JAR từ `runtimeClasspath`.

Một application có external dependency:

~~~kotlin
plugins {
    id("application")
}

dependencies {
    implementation("org.example:codec:1.0")
}
~~~

`org.example:codec:1.0` ở đây là dependency **giả để minh họa cú pháp**, không có trong project runnable. Nếu code cần codec ở runtime, `gradle run` thường hoạt động vì plugin Application tạo classpath có dependency, trong khi `java -jar` với thin JAR có thể lỗi `NoClassDefFoundError`.

### 7.2. Distribution của Application plugin

~~~bash
./gradlew installDist
./gradlew distZip
~~~

Layout tiêu biểu:

~~~text
build/install/app-name/
├── bin/
│   ├── app-name
│   └── app-name.bat
└── lib/
    ├── app-name-version.jar
    └── runtime-library.jar
~~~

Startup scripts dựng runtime classpath tới `lib/`. Để QA distribution:

1. Build `distZip`, tìm đúng ZIP output.
2. Liệt kê entries và scripts executable.
3. Kiểm đủ runtime JARs và không có test-only deps.
4. Extract vào thư mục sạch, giữ permissions khi cần.
5. Chạy startup script **bên trong distribution**, không chỉ `gradle run`.
6. Test trên target OS/JDK/container.

### 7.3. Fat JAR, Shadow và Spring Boot

- Shadow JAR có thể gộp class/resources, relocations và service file transformers.
- Spring Boot executable JAR thường chứa `BOOT-INF/classes`, `BOOT-INF/lib`, launcher phù hợp.
- WAR có `WEB-INF/classes`, `WEB-INF/lib` và cần servlet container.
- Android APK/AAB có quy trình tooling khác, không là plain JAR.

**Không sử dụng validator thin JAR ở mục 10 nguyên xi cho Boot JAR**. Chẳng hạn việc phát hiện nested JAR phải được coi là bình thường ở `BOOT-INF/lib`, trong khi bài lab quy định thin JAR không có nested dependencies.

### 7.4. Dependency report không chứng minh packaging

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency some-module --configuration runtimeClasspath
~~~

Hai lệnh mô tả resolved dependency graph. Muốn biết những JARs thật sự **đã nằm trong ZIP/Boot JAR/distribution**, phải inspect chính artifact và chạy thử. Nếu release phụ thuộc classpath, test một consumer thực tế.

## 8. Project Java 17 chạy được: artifact có manifest, resource và smoke test

Ví dụ không có external dependency, cần một JDK 17 và Gradle tương thích. Dùng `application` plugin, Gradle Kotlin DSL.

### 8.1. Cấu trúc đầy đủ

~~~text
release-artifact-lab/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── release/
        │           └── Main.java
        └── resources/
            └── release.properties
~~~

### 8.2. settings.gradle.kts

~~~kotlin
rootProject.name = "release-artifact-lab"
~~~

### 8.3. src/main/java/demo/release/Main.java

~~~java
package demo.release;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();

        try (InputStream input =
                     Main.class.getResourceAsStream("/release.properties")) {
            if (input == null) {
                throw new IOException("Missing release.properties");
            }
            properties.load(input);
        }

        String channel = properties.getProperty("release.channel");
        String version = properties.getProperty("release.version");
        if (channel == null || version == null) {
            throw new IOException("Incomplete release.properties");
        }

        System.out.println("Artifact smoke test OK");
        System.out.println("channel=" + channel);
        System.out.println("version=" + version);
    }
}
~~~

Java 17 hợp lệ. Chương trình chủ động fail nếu resource không được đóng gói; nhờ vậy smoke test có giá trị phát hiện lỗi packaging.

### 8.4. src/main/resources/release.properties

~~~properties
release.channel=stable
release.version=1.0.0
~~~

Dùng ASCII nên `Properties.load(InputStream)` đọc đúng. Nếu real properties dùng Unicode, cần xác định encoding/escaping phù hợp.

### 8.5. build.gradle.kts tối thiểu tạo JAR

~~~kotlin
import org.gradle.api.tasks.bundling.Jar
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    id("application")
}

group = "demo.release"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}

application {
    mainClass.set("demo.release.Main")
}

tasks.named<Jar>("jar") {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
    manifest {
        attributes["Main-Class"] = "demo.release.Main"
        attributes["Implementation-Title"] = "release-artifact-lab"
        attributes["Implementation-Version"] = project.version.toString()
    }
}
~~~

Đây là bản **tối thiểu để build và chạy**. Mục 10 trình bày **toàn bộ build.gradle.kts thay thế** có typed validator; **không nối hai bản thành một file**, tránh lặp `plugins`.

### 8.6. Build và chạy JAR

Trong project mới, nếu chưa có Wrapper, dùng bản Gradle cài sẵn:

~~~bash
gradle clean jar
java -jar build/libs/release-artifact-lab-1.0.0.jar
~~~

Stdout **chính xác của Java program**:

~~~text
Artifact smoke test OK
channel=stable
version=1.0.0
~~~

Nếu đã có Wrapper được tạo/commit, dùng `./gradlew clean jar` hoặc `gradlew.bat clean jar`.

### 8.7. Kết quả jar list

~~~bash
jar --list --file build/libs/release-artifact-lab-1.0.0.jar
~~~

Tìm các entries:

~~~text
META-INF/MANIFEST.MF
demo/release/Main.class
release.properties
~~~

Các directory entries hoặc dòng khác có thể xuất hiện; đây không phải stdout đầy đủ.

### 8.8. Kiểm tra Java source bằng javac/java độc lập

Linux/macOS:

~~~bash
mkdir -p out
javac --release 17 -d out src/main/java/demo/release/Main.java
cp src/main/resources/release.properties out/release.properties
java -cp out demo.release.Main
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -d out src\main\java\demo\release\Main.java
Copy-Item src\main\resources\release.properties out\release.properties
java -cp out demo.release.Main
~~~

Stdout giống mục 8.6. Đây chỉ là kiểm tra code Java/resource classpath; **không chứng minh manifest hoặc ZIP của Gradle đã đúng**.

## 9. Vì sao phải có một Gradle verification task?

Thủ công `jar tf`/`javap`/`java -jar` rất hữu ích lúc debug, nhưng release gate cần **tự động chặn** khi:

- Sai Main-Class hay version.
- Thiếu class/resource.
- Bytecode target vượt policy.
- Artifact hỏng/không có.
- Duplicate ZIP entries.
- Có entry name không an toàn.
- Chứa nested dependency JAR ngoài policy thin JAR của lab.

Một task verification tốt nên:

1. Có inputs rõ, đặc biệt **`@InputFile` từ artifact producer**.
2. Không đoán đường dẫn file.
3. Không sửa artifact đang kiểm.
4. Fail bằng exception hoặc exit nonzero khi policy không đạt.
5. Không silently ignore mismatch.
6. Được nối vào `check` và publish/CI gate có chủ đích.
7. Sử dụng APIs tách biệt với Gradle Project trong `@TaskAction` để thuận lợi cho Configuration Cache.
8. Không tuyên bố một check giới hạn là full security scanner.

## 10. build.gradle.kts hoàn chỉnh có verifyReleaseJar

Thay **toàn bộ** nội dung `build.gradle.kts` của mục 8.5 bằng bản sau. Hai file Java/resource và `settings.gradle.kts` giữ nguyên.

~~~kotlin
import java.io.DataInputStream
import java.util.Properties
import java.util.jar.Manifest
import java.util.zip.ZipFile
import org.gradle.api.DefaultTask
import org.gradle.api.GradleException
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.api.tasks.bundling.Jar
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    id("application")
}

group = "demo.release"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}

application {
    mainClass.set("demo.release.Main")
}

tasks.named<Jar>("jar") {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
    manifest {
        attributes["Main-Class"] = "demo.release.Main"
        attributes["Implementation-Title"] = "release-artifact-lab"
        attributes["Implementation-Version"] = project.version.toString()
    }
}

abstract class VerifyReleaseJar : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val artifactFile: RegularFileProperty

    @get:Input
    abstract val expectedMainClass: Property<String>

    @get:Input
    abstract val expectedVersion: Property<String>

    @get:Input
    abstract val expectedChannel: Property<String>

    @TaskAction
    fun verify() {
        val file = artifactFile.get().asFile
        if (!file.isFile || file.length() == 0L) {
            throw GradleException("Release JAR missing or empty: " + file)
        }

        ZipFile(file).use { zip ->
            val names = zip.entries().asSequence()
                .map { it.name }.toList()

            if (names.size != names.toSet().size) {
                throw GradleException("Duplicate entry names")
            }

            val unsafe = names.firstOrNull { name ->
                name.startsWith("/") ||
                    '\\' in name ||
                    name.split('/').any { it == ".." }
            }
            if (unsafe != null) {
                throw GradleException("Unsafe entry: " + unsafe)
            }

            val manifestEntry = zip.getEntry("META-INF/MANIFEST.MF")
                ?: throw GradleException("Missing manifest")
            val manifest = zip.getInputStream(manifestEntry).use {
                Manifest(it)
            }
            val main = manifest.mainAttributes.getValue("Main-Class")
            val version = manifest.mainAttributes.getValue(
                "Implementation-Version"
            )
            if (main != expectedMainClass.get()) {
                throw GradleException("Main-Class mismatch: " + main)
            }
            if (version != expectedVersion.get()) {
                throw GradleException(
                    "Implementation-Version mismatch: " + version
                )
            }

            val classPath = expectedMainClass.get()
                .replace('.', '/') + ".class"
            val classEntry = zip.getEntry(classPath)
                ?: throw GradleException("Missing class: " + classPath)

            zip.getInputStream(classEntry).use { stream ->
                DataInputStream(stream).use { data ->
                    if (data.readInt() != 0xCAFEBABE.toInt()) {
                        throw GradleException("Invalid class header")
                    }
                    val minor = data.readUnsignedShort()
                    val major = data.readUnsignedShort()
                    if (major != 61 || minor != 0) {
                        throw GradleException(
                            "Wrong class version: " + major + "." + minor
                        )
                    }
                }
            }

            val resource = zip.getEntry("release.properties")
                ?: throw GradleException("Missing release.properties")
            val props = Properties()
            zip.getInputStream(resource).use { props.load(it) }

            if (props.getProperty("release.channel") !=
                expectedChannel.get()
            ) {
                throw GradleException("Wrong release.channel")
            }
            if (props.getProperty("release.version") !=
                expectedVersion.get()
            ) {
                throw GradleException("Wrong release.version")
            }

            val nestedJar = names.firstOrNull {
                it.lowercase().endsWith(".jar")
            }
            if (nestedJar != null) {
                throw GradleException(
                    "Unexpected nested JAR: " + nestedJar
                )
            }
        }

        logger.lifecycle("RELEASE JAR VERIFIED: " + file.name)
    }
}

val verifyReleaseJar = tasks.register<VerifyReleaseJar>(
    "verifyReleaseJar"
) {
    group = "verification"
    description = "Validates release JAR content and metadata"

    artifactFile.set(
        tasks.named<Jar>("jar").flatMap { it.archiveFile }
    )
    expectedMainClass.set("demo.release.Main")
    expectedVersion.set(project.version.toString())
    expectedChannel.set("stable")
}

tasks.named("check") {
    dependsOn(verifyReleaseJar)
}
~~~

### 10.1. Tại sao code này nối đúng jar task?

~~~kotlin
artifactFile.set(
    tasks.named<Jar>("jar").flatMap { it.archiveFile }
)
~~~

`jar` là producer; `artifactFile` là input Gradle theo dõi. Provider mang theo thông tin task dependency nên Gradle lập lịch build JAR trước validator. Không cần `dependsOn("jar")` thủ công nếu Gradle đã suy ra dependency từ task output provider đúng cách.

### 10.2. Tại sao có @InputFile và @Input?

- `@get:InputFile`: file JAR cần kiểm.
- `@get:PathSensitive(PathSensitivity.NONE)`: validation theo nội dung, không phụ thuộc đường tuyệt đối của file.
- `@get:Input expectedMainClass`: đổi contract Main-Class phải được đánh giá lại.
- `@get:Input expectedVersion`: đổi release version không bị bỏ qua.
- `@get:Input expectedChannel`: policy `stable` trở thành input rõ ràng.
- `@TaskAction`: đọc data từ task properties, không truy cập Project API trực tiếp trong execution.

Task không khai báo `@OutputFile` vì mục đích **read-only verification**, không sinh artifact khác. Nó được yêu cầu chạy khi `check` chạy, phù hợp release quality gate.

### 10.3. Kiểm tra duplicates và Zip Slip

~~~kotlin
val names = zip.entries().asSequence().map { it.name }.toList()
if (names.size != names.toSet().size) {
    throw GradleException("Duplicate entry names")
}
~~~

Không chỉ gọi `zip.getEntry("release.properties")`; nếu archive có hai entries cùng tên, `getEntry` có thể chỉ phản ánh một entry được chọn bởi thư viện đọc. Cần scan danh sách để biết duplicates tồn tại.

Check đường dẫn `/`, backslash và `..` segment là **policy cơ bản của lab**; artifact untrusted ở môi trường thực cần thêm protections (Windows drive paths, symlinks, Unicode path normalization, uncompressed size limits). Validator không phải một full archive security scanner.

### 10.4. Kiểm tra manifest và bytecode

`java.util.jar.Manifest` parse metadata đúng chuẩn; so `Main-Class` và `Implementation-Version` với expected values. `DataInputStream` đọc 8 bytes đầu của class file:

~~~text
CA FE BA BE | minor version (2 bytes) | major version (2 bytes)
~~~

`0xCAFEBABE.toInt()` so đúng 32-bit pattern. `major=61, minor=0` là expected Java 17 bytecode thường trong lab.

**Giới hạn rõ ràng:** Validator kiểm một Main.class. Với production JAR chứa nhiều classes/dependency JARs, phải mở rộng để kiểm **mọi class** và xét multi-release rules, không tuyên bố rằng kiểm Main.class bảo đảm toàn bộ dependency graph Java17-compatible.

### 10.5. Kiểm tra resource values và version

`release.properties` nằm đúng root JAR; validator parse bằng `Properties`, so:

~~~text
release.channel=stable
release.version=1.0.0
~~~

Nếu project.version đổi mà resource không đổi, validator fail. Chính sách tốt hơn cho production là có **một nguồn version chuẩn** và task sinh metadata từ input được khai báo, thay vì nhập cùng version thủ công ở nhiều nơi.

### 10.6. Check task và fail-fast cho release

~~~kotlin
tasks.named("check") {
    dependsOn(verifyReleaseJar)
}
~~~

Với Java/Application plugin, `check` là lifecycle task thuộc nhóm verification. Sau đó:

~~~bash
gradle clean check
~~~

sẽ buộc artifact validation nằm trong graph. Nếu archive thiếu Main/resource hoặc sai version, `GradleException` làm task fail và build không được phép coi là `check passed`.

Chạy riêng:

~~~bash
gradle clean verifyReleaseJar
~~~

Một dòng do task tạo ra khi dùng lifecycle logging:

~~~text
RELEASE JAR VERIFIED: release-artifact-lab-1.0.0.jar
~~~

Đây **không phải stdout đầy đủ của Gradle**; còn có task outcomes và log tùy Gradle version. Khi bật `-q`, lifecycle log này có thể bị lọc, không có nghĩa task chưa chạy.

### 10.7. Smoke test trên chính JAR

~~~bash
gradle clean check
java -jar build/libs/release-artifact-lab-1.0.0.jar
~~~

Stdout Java **chính xác**:

~~~text
Artifact smoke test OK
channel=stable
version=1.0.0
~~~

Lý do cần `java -jar`: `gradle run` dùng source set runtime classpath; nó không chắc đã kiểm manifest và archive đúng. Vì project lab không có dependency ngoài, JAR có thể chạy trực tiếp; với thin JAR của ứng dụng có external libs, phải test distribution/packaging contract thay thế.

## 11. Thử nghiệm cố ý làm release gate thất bại

Các ví dụ dưới đây **cố ý gây lỗi** để kiểm tra gate. Khôi phục file/build script về trạng thái mục 8–10 sau mỗi thí nghiệm.

### 11.1. Manifest sai Main-Class

Đổi:

~~~kotlin
attributes["Main-Class"] = "demo.release.WrongMain"
~~~

giữ `expectedMainClass="demo.release.Main"`. Chạy:

~~~bash
gradle clean verifyReleaseJar
~~~

Validator phải fail với `Main-Class mismatch`. Nếu bỏ validator rồi chạy `java -jar`, JVM có thể không tìm thấy main class.

### 11.2. Resource thiếu

Đổi tên `src/main/resources/release.properties` thành `release.properties.bak` (hoặc loại nó khỏi source set). `compileJava` vẫn có thể pass, nhưng `verifyReleaseJar` fail `Missing release.properties`. Điều này chứng minh **compile thành công không đảm bảo resources đã vào artifact**.

### 11.3. Release version sai

Đổi:

~~~kotlin
version = "1.0.1"
~~~

nhưng file resource vẫn chứa `release.version=1.0.0`. Expected version lấy từ project là 1.0.1; validator sẽ fail. Đó là lỗi cần bắt vì artifact tự mâu thuẫn identity.

### 11.4. Bytecode target sai

Nếu có JDK 21 compiler và Gradle tương thích, đặt Java toolchain/release21 để tạo class major65. Validator của lab quy định major61, nên fail. Nếu vẫn chạy javac17 với `--release 21`, build fail sớm vì compiler không hỗ trợ target tương lai. **Hai failure khác nhau** và đều cần chẩn đoán đúng.

### 11.5. Duplicate entry

Nếu copy specs tạo hai entries cùng tên, Gradle có thể từ chối sớm theo `DuplicatesStrategy.FAIL`, hoặc JAR có duplicate nếu plugin cho phép. Validator sẽ kiểm names và fail. Đừng dùng `EXCLUDE` vô điều kiện với service files của fat JAR: có thể cần merge transform.

### 11.6. Sai artifact type

Áp validator thin JAR vào Spring Boot JAR có nested `BOOT-INF/lib/*.jar` sẽ bị từ chối do nested jar policy. **Đó là validator sai loại artifact**, không có nghĩa Spring Boot packaging sai. Cần thiết kế riêng cho Boot JAR.

## 12. Groovy DSL tương đương

Phần build + manifest của project mẫu khi dùng `build.gradle` thay cho `build.gradle.kts`:

~~~groovy
plugins {
    id 'application'
}

group = 'demo.release'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

application {
    mainClass = 'demo.release.Main'
}

tasks.named('jar', Jar) {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
    manifest {
        attributes(
            'Main-Class': 'demo.release.Main',
            'Implementation-Title': 'release-artifact-lab',
            'Implementation-Version': project.version.toString()
        )
    }
}
~~~

`settings.gradle` tương ứng:

~~~groovy
rootProject.name = 'release-artifact-lab'
~~~

Giữ nguyên `Main.java` và `release.properties`. Groovy example này tạo **cùng loại JAR**, nhưng **chưa có full typed `verifyReleaseJar`** như bản Kotlin DSL của mục 10.

Để kiểm tra một subset điều kiện bằng Groovy DSL:

~~~groovy
import java.util.jar.Manifest
import java.util.zip.ZipFile

tasks.register('verifyReleaseJarGroovy') {
    def producer = tasks.named('jar', Jar)
    def fileProvider = producer.flatMap { it.archiveFile }
    inputs.file(fileProvider)

    doLast {
        ZipFile(fileProvider.get().asFile).withCloseable { zip ->
            def entry = zip.getEntry('META-INF/MANIFEST.MF')
            if (entry == null) {
                throw new GradleException('Missing manifest')
            }
            def manifest = zip.getInputStream(entry)
                .withCloseable { new Manifest(it) }
            if (manifest.mainAttributes.getValue('Main-Class') !=
                'demo.release.Main'
            ) {
                throw new GradleException('Wrong Main-Class')
            }
            if (zip.getEntry('demo/release/Main.class') == null) {
                throw new GradleException('Missing Main.class')
            }
            if (zip.getEntry('release.properties') == null) {
                throw new GradleException('Missing release.properties')
            }
        }
    }
}

tasks.named('check') {
    dependsOn 'verifyReleaseJarGroovy'
}
~~~

**Giới hạn:** Snippet Groovy chỉ kiểm manifest, class và resource; **không** so duplicates/path traversal/bytecode/version/resource values như full Kotlin task. Trong build lớn, nên trích validator thành convention plugin/task type tái sử dụng để hai DSL dùng chung một logic release.

## 13. Kiểm tra distribution và runtime dependencies

### 13.1. Install distribution

Trong project lab có Application plugin:

~~~bash
gradle installDist
~~~

Trên Linux/macOS, với tên project mẫu:

~~~bash
./build/install/release-artifact-lab/bin/release-artifact-lab
~~~

Trên Windows:

~~~bat
build\install\release-artifact-lab\bin\release-artifact-lab.bat
~~~

Dạng output Java giống smoke test:

~~~text
Artifact smoke test OK
channel=stable
version=1.0.0
~~~

Đây là **layout dự kiến** theo Application plugin conventions. Nếu project đổi application/distribution name hoặc script path, phải kiểm tra output thực thay vì sao chép đường dẫn cứng.

### 13.2. distZip phải đóng đủ lib và scripts

~~~bash
gradle distZip
~~~

Kiểm tra đúng ZIP dưới `build/distributions`, ví dụ:

~~~text
build/distributions/release-artifact-lab-1.0.0.zip
~~~

Liệt kê và xem `bin/`, `lib/`; extract vào clean directory, chạy startup script. Một ZIP distribution có thể khác JAR `build/libs`, nên cần gate riêng. Đừng chỉ verify `jar` rồi khẳng định toàn distribution đã pass.

### 13.3. Multi-project build

Với project `:library` và `:app`, có thể cần:

~~~bash
./gradlew :library:jar
./gradlew :library:check
./gradlew :app:distZip
~~~

Mỗi artifact type/project có contract khác nhau. `tasks.withType<Jar>().configureEach` cấu hình JARs trong **project hiện tại**, không tự sửa mọi subproject. Dùng convention plugin để chia sẻ release policies.

### 13.4. Missing runtime dependencies

Dùng:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency lib-name --configuration runtimeClasspath
~~~

Sau đó kiểm chứng các runtime libraries **thực sự có** trong distribution hoặc fat JAR. Dependency report phản ánh resolution graph, không tự chứng minh output ZIP/Boot JAR đã chứa đủ.

### 13.5. Container image

Nếu artifact deploy trong container, cần kiểm:

- Container JRE version so với class major.
- Working directory và file/resource paths.
- Runtime libraries bên trong image.
- Env variables, permissions, filesystem read-only behavior.
- Entry point/startup flags và health check.

`java -jar` trên laptop không thay thế việc smoke test trong image nếu image có runtime/OS khác.

## 14. Maven Publish: kiểm artifact và metadata đã tạo

### 14.1. Library publication không chỉ có JAR

Gradle Maven publication thường gồm:

- Primary JAR.
- Maven POM với groupId/artifactId/version/dependencies.
- Gradle Module Metadata cho variant-aware consumers.
- Sources/Javadoc JAR nếu bật.
- Checksums/signatures tùy Gradle và repository configuration.

Một library có thể chạy tốt khi project khác dùng `project(":library")` nhưng fail khi người tiêu thụ tải module Maven từ repository, do metadata `api`/`implementation` khác mong đợi.

### 14.2. Mẫu publication riêng cho library

Đây là **snippet ở project library khác**, không ghép vào Application project lab:

~~~kotlin
import org.gradle.api.publish.maven.MavenPublication

plugins {
    id("java-library")
    id("maven-publish")
}

group = "demo.library"
version = "1.0.0"

java {
    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }
}
~~~

Cấu hình này chưa chỉ định repository đích hoặc credentials; không tự publish lên Internet.

### 14.3. Generate metadata để đọc trước publish

~~~bash
./gradlew generatePomFileForMavenJavaPublication
./gradlew generateMetadataFileForMavenJavaPublication
~~~

Tùy plugin/version, output nằm dưới:

~~~text
build/publications/mavenJava/pom-default.xml
build/publications/mavenJava/module.json
~~~

Cần kiểm coordinates, compile/runtime dependency scopes, capabilities/attributes, version constraints và artifacts đúng. Không chỉnh generated file rồi coi là fix bền vững; sửa publication configuration.

### 14.4. Staging + consumer test

Quy trình đáng tin cậy:

1. Tạo primary JAR và metadata.
2. Chạy unit/integration/ABI tests và archive validation.
3. Publish vào một **staging repository/test directory**.
4. Đọc files ở staging, xác nhận JAR, POM, module.json, sources/Javadoc, checksums.
5. Tạo consumer project độc lập phụ thuộc artifact từ staging.
6. Compile/run consumer trên JDK mục tiêu.
7. Chỉ promote lên repository chính thức khi stage pass.

Đừng upload lại cùng một immutable release coordinate với bytes khác nếu policy repository cấm overwrite. Nó phá tính truy nguyên và có thể gây downstream cache inconsistency.

## 15. License, NOTICE, SBOM và secrets

### 15.1. Rà soát nội dung không được phát hành

Một số files nên bị chặn nếu xuất hiện trong artifact:

~~~text
.env
secret.properties
credentials.json
private.key
application-local.properties
test-database-dump.sql
~~~

Đây là ví dụ danh mục; chính sách thực tế phải phân biệt dữ liệu test công khai với credentials thật. Nếu một secret đã bị phát hành, việc xóa JAR sau đó **không đủ**: cần rotate/revoke secret theo quy trình.

### 15.2. Licenses và NOTICE

Khi gộp third-party components vào fat JAR/distribution, kiểm tra obligations của licenses và NOTICE files. Một file `META-INF/LICENSE` trùng tên không nhất thiết được phép bỏ; có thể cần merge/rename để giữ các notices khác nhau.

SBOM (Software Bill of Materials) có thể dùng CycloneDX/SPDX để mô tả thành phần, versions, identifiers và hashes. Gradle không tự tạo một SBOM đầy đủ chỉ bằng plugin Java; cần tooling phù hợp và verify SBOM phản ánh **release packaging thực tế**.

### 15.3. Dependency verification khác release artifact verification

`gradle/verification-metadata.xml` kiểm external dependencies được Gradle download theo metadata trust; nó không chứng minh `Main-Class` của JAR bạn vừa build đúng. Cần cả hai:

| Lớp | Mục tiêu |
| --- | --- |
| Dependency locking | Selected dependency versions được kiểm soát |
| Dependency verification | Downloaded artifacts có bytes/chữ ký đúng giá trị tin cậy |
| Artifact validator | JAR/ZIP do project build có nội dung/contract đúng |
| Smoke/integration tests | Artifact thực tế được consumer/runtime sử dụng đúng |
| Release checksum/signing | Bytes cuối và provenance được xác minh |
| SBOM/compliance | Thành phần/giấy phép phù hợp policy |

Checksum **không chứng minh source sạch**, và sự hiện diện của chữ ký **không đủ** nếu chưa xác minh trusted signer/key.

## 16. SHA-256, signing và “đúng bytes” sau khi upload

### 16.1. Tính SHA-256

Linux:

~~~bash
sha256sum build/libs/release-artifact-lab-1.0.0.jar
~~~

macOS:

~~~bash
shasum -a 256 build/libs/release-artifact-lab-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
(Get-FileHash .\build\libs\release-artifact-lab-1.0.0.jar -Algorithm SHA256).Hash
~~~

Kết quả hash phụ thuộc **bytes thực tế**. Không đặt một hash hex giả làm expected output trong tài liệu.

### 16.2. Ghi checksum file

~~~bash
sha256sum build/libs/release-artifact-lab-1.0.0.jar \
  > release-artifact-lab-1.0.0.jar.sha256
~~~

Và có thể kiểm tra từ đúng working directory:

~~~bash
sha256sum --check release-artifact-lab-1.0.0.jar.sha256
~~~

Checksum record chứa đường tương đối của file; nếu di chuyển JAR, phải điều chỉnh path tương ứng hoặc tính/check hash trực tiếp. Cần lưu record từ bytes **sau cùng**, không trước một task transform khác.

### 16.3. Signatures và provenance

Một release có thể được kèm:

~~~text
release-artifact-lab-1.0.0.jar
release-artifact-lab-1.0.0.jar.sha256
release-artifact-lab-1.0.0.jar.asc
sbom.json
provenance.json
~~~

Đây là **cấu trúc minh họa**, không phải yêu cầu mặc định của Gradle. `.asc` cần xác minh bằng trusted public key/identity, không chỉ kiểm file tồn tại.

Không ghi signing private key/passphrase vào repo hoặc build logs. Có thể dùng Gradle Signing plugin hoặc hệ signing/attestation của CI theo policy.

### 16.4. Time-of-check/time-of-use

Nên tránh quy trình:

~~~text
Build jar A -> Verify jar A -> Rebuild jar B -> Upload jar B
~~~

Nếu jar B khác jar A, QA không còn áp dụng cho bytes được upload.

Quy trình tốt:

~~~text
Build once -> Verify exact artifact -> SHA-256 -> Store immutable pipeline artifact
                                         |
                                         v
                                Check hash -> Upload -> Verify remote hash
~~~

Release stage nên sử dụng **đúng file** đã qua QA, không rebuild âm thầm. Nếu Gradle publication task tạo output dựa trên task khác, nối gate với producer của **publication artifact** đó.

## 17. Reproducible archives: so sánh hai clean builds

### 17.1. Gradle 9 có mặc định mới

Theo tài liệu Gradle, **từ Gradle 9.0.0**, `AbstractArchiveTask` như `Jar`/`Zip` tạo archives reproducible theo mặc định: file order deterministic, timestamps cố định, permissions chuẩn hóa. Với Gradle cũ hoặc để nêu rõ policy, đặt:

~~~kotlin
tasks.withType<Jar>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Nhưng nếu một generated resource có `Instant.now()`/UUID/absolute path, JAR vẫn có thể khác SHA-256 vì **nội dung entry** thay.

### 17.2. Kiểm repeatability ở một máy

Linux/macOS có `sha256sum`:

~~~bash
gradle --no-build-cache clean jar
sha256sum build/libs/release-artifact-lab-1.0.0.jar \
  | cut -d ' ' -f 1 > first.sha

gradle --no-build-cache clean jar
sha256sum build/libs/release-artifact-lab-1.0.0.jar \
  | cut -d ' ' -f 1 > second.sha

cmp first.sha second.sha
~~~

Nếu `cmp` exit code 0, hai hashes trùng. `--no-build-cache` tránh việc chỉ so một cached output; `clean` buộc tạo JAR lại từ inputs.

Windows PowerShell:

~~~powershell
gradle --no-build-cache clean jar
$first = (Get-FileHash .\build\libs\release-artifact-lab-1.0.0.jar -Algorithm SHA256).Hash

gradle --no-build-cache clean jar
$second = (Get-FileHash .\build\libs\release-artifact-lab-1.0.0.jar -Algorithm SHA256).Hash

if ($first -ne $second) {
    throw "Release JAR is not repeatable"
}
~~~

### 17.3. Kiểm reproducibility mạnh hơn

Hai lần chạy trong cùng folder chỉ chứng minh repeatability tại môi trường ấy. Muốn kiểm qua máy/CI:

1. Checkout cùng commit vào **hai workspaces độc lập**.
2. Dùng cùng Gradle Wrapper, toolchain JDK và compiler flags.
3. Pin plugins, dependencies, lockfiles và repository integrity.
4. Kiểm soát environment, locale/timezone, generated inputs.
5. Chạy clean builds không dùng build cache.
6. So SHA-256 của cùng artifact type và target platform.
7. Nếu khác, diff ZIP entries, manifest, classes, resources, timestamps/order và permissions.
8. Khi sửa xong, giữ regression job trong CI.

Nếu **input thật sự đổi** (release version, channel, platform), hash đổi là đúng. Reproducibility không yêu cầu mọi input khác nhau tạo cùng bytes.

## 18. CI pipeline: đưa artifact QA thành gate bắt buộc

Một pipeline release có thể gồm:

~~~text
Checkout source / lockfiles / Wrapper
              |
              v
      Compile + unit tests
              |
              v
        Package artifact
              |
              v
    verifyReleaseJar / archive QA
              |
              v
      Smoke test exact JAR
              |
              v
  Metadata/License/SBOM review
              |
              v
   SHA-256 + signing/provenance
              |
              v
      Staging consumer test
              |
              v
       Publish / promote
~~~

### 18.1. Shell pipeline tối thiểu cho lab

~~~bash
set -e
gradle --no-build-cache clean check
java -jar build/libs/release-artifact-lab-1.0.0.jar
sha256sum build/libs/release-artifact-lab-1.0.0.jar
~~~

Đây là Bash snippet cho lab, **không phải full CI config**; PowerShell có cú pháp kiểm lỗi riêng. `check` đã phụ thuộc `verifyReleaseJar` nên archive sai khiến CI dừng trước bước publish.

### 18.2. Fail phải là exit code khác 0

Đừng viết validator chỉ in:

~~~text
WARNING: Missing release.properties
~~~

rồi để task thành công. CI quality gate cần **năng lực chặn**; `GradleException` trong `@TaskAction` làm build fail. Cũng không dùng `ignoreFailures=true` hoặc tiếp tục publish sau lỗi policy mà chưa có quyết định cho phép rõ ràng.

### 18.3. Khi có nhiều artifacts

Nếu project phát hành cả `jar`, `sourcesJar`, `javadocJar`, `distZip`, mỗi loại có contract khác nhau. Có thể dùng convention plugin tạo các validation tasks có inputs từ đúng producer, chứ không hard-code một class/path áp dụng cho tất cả.

### 18.4. Staging consumer test

Với library Maven, test thêm một consumer độc lập từ staging repository. Nó có thể phát hiện lỗi metadata `api`/`implementation` hoặc artifact version mà unit tests nội bộ không thấy.

### 18.5. Kiểm tra trước và sau upload

Tính hash artifact sau build/QA, lưu checksum, kiểm lại ngay trước upload, rồi nếu có thể download artifact công khai để so hash. Điều này bảo vệ against upload nhầm file hoặc overwrite.

## 19. Troubleshooting: nguyên nhân và cách xử lý

| Triệu chứng | Nguyên nhân hay gặp | Hướng xử lý |
| --- | --- | --- |
| `jar tf` báo không đọc file | File hỏng, sai path, chưa build | Xác định producer `archiveFile`, chạy task, kiểm ZIP integrity |
| `no main manifest attribute` | Executable JAR thiếu Main-Class | Thêm manifest hoặc test đúng artifact type |
| `Could not find or load main class` | Manifest sai tên/package hoặc class thiếu | So `Main-Class` với JAR entries |
| `Missing release.properties` | `processResources`/CopySpec sai | Kiểm resources root/path và excludes |
| `UnsupportedClassVersionError` | Bytecode cao hơn runtime | Toolchain/`--release`, test JDK thấp nhất |
| `NoClassDefFoundError` khi `java -jar` | Thin JAR thiếu runtime dependencies | Distribution/fat JAR hoặc classpath phù hợp |
| Duplicate class/services | Merge/copy conflicts | Fail duplicate hoặc merge đúng service files |
| Version trong manifest khác filename | Hai nguồn version không đồng bộ | Một nguồn version + automatic validation |
| JAR có token/secret | Resource/include quá rộng | Chặn upload, loại file, rotate leaked token |
| SHA khác giữa clean builds | Generated time/paths/JDK/archive metadata | Kiểm reproducibility inputs/entries |
| POM đúng nhưng consumers fail | Module Metadata/variants/deps khác | Consumer test từ staging |
| Upload đúng tên nhưng hash khác | Rebuild sau QA, artifact khác, overwrite | Immutable artifact + before/after hash |
| Gradle run pass nhưng distribution fail | Startup scripts/lib contents sai | Extract và chạy distribution thật |
| `bootJar` fail thin JAR policy | Validator áp nhầm artifact type | Dùng Boot-specific layout/runtime checks |
| `verifyReleaseJar` bị skip khi chỉ chạy publish | Publish không phụ thuộc QA gate | Nối dependency CI/publish tới gate |
| Sources/Javadoc JAR thiếu | Không bật hoặc chưa publish đúng variants | `withSourcesJar()`/`withJavadocJar()` và inspect publication |
| Checksum hợp lệ nhưng signer lạ | Trust model chưa xác minh | Xác minh PGP/sigstore identity đáng tin |

### 19.1. Không sửa bằng cách xóa mọi cache

Nếu manifest thiếu `Main-Class` hay resource bị exclude, xóa `~/.gradle` không thay đổi build logic. Bắt đầu từ artifact hiện tại và task producer, dùng clean build/stacktrace khi cần.

### 19.2. Không “chữa” bằng đổi đúng tên file

Đổi filename trên disk từ `app-0.9.jar` thành `app-1.0.jar` không làm nội dung/version/metadata của JAR đổi. Phải rebuild từ đúng inputs và publication version, verify rồi mới publish.

### 19.3. Không lờ một lỗi để ra mắt cho kịp

Một JAR được ký hay có SBOM không tự chữa runtime dependency thiếu. Mỗi failed quality gate cần được xử lý theo policy hoặc chấp thuận ngoại lệ rõ, không chỉ thay warning severity.

## 20. Hai mươi bài tập có đáp án

### Bài 1. Artifact nào được publish?

Build có cả `jar` và `shadowJar`; publication trỏ tới `shadowJar`. Nên verify file nào?

**Đáp án:** Output của `shadowJar` và publication metadata tương ứng, không chỉ `jar`.

### Bài 2. Library không có Main-Class

`library.jar` không có `Main-Class`. Có bị lỗi?

**Đáp án:** Không nếu library không cần executable entry point. Check contract library thay vì application.

### Bài 3. Main class path

`package demo.release; public class Main` có đường entry nào?

**Đáp án:** `demo/release/Main.class`.

### Bài 4. Resource thiếu

`Main.class` có mặt nhưng `release.properties` không nằm trong archive.

**Đáp án:** Kiểm `processResources`, source set resources, includes/excludes và packaging. Validator phải fail.

### Bài 5. Bytecode target

`javap` ghi `major version: 65`, runtime tối thiểu Java17.

**Đáp án:** Không đáp ứng contract; Java17 tối đa hiểu major61. Recompile target17 nếu hợp lệ hoặc thay yêu cầu runtime có chủ đích.

### Bài 6. Thin JAR

`gradle run` pass, `java -jar` lỗi thiếu external class.

**Đáp án:** Thin JAR không tự chứa runtime dependencies. Test/publish distribution, fat JAR hoặc cung cấp classpath theo thiết kế.

### Bài 7. Manifest-Version

`Manifest-Version: 1.0` có chứng minh app release version 1.0.0?

**Đáp án:** Không. Đây là version định dạng manifest, cần kiểm `Implementation-Version`/publication version.

### Bài 8. Duplicate services

Fat JAR có hai `META-INF/services` entries cùng tên.

**Đáp án:** Không exclude một file ngẫu nhiên; dùng merge transformer thích hợp và test `ServiceLoader`.

### Bài 9. Đúng source nhưng SHA khác

Hai clean builds cùng commit tạo khác SHA.

**Đáp án:** Kiểm timestamps/order, generated files, JDK, plugins/dependencies, env/locale/paths và archive entries. Không mặc định Gradle bug.

### Bài 10. Hash trước upload khác sau download

**Đáp án:** Dừng release, điều tra sai file/overwrite/transform/proxy. Checksum phải bảo vệ đúng artifact bytes.

### Bài 11. Thực hiện verifyReleaseJar

Có typed task nối `artifactFile.set(jar.flatMap { it.archiveFile })`. Ưu điểm?

**Đáp án:** Gradle xác định file producer thật và suy ra task dependency; ít hard-code path.

### Bài 12. Version sai

Project.version=1.0.1, resource=1.0.0.

**Đáp án:** Gate fail; đồng bộ version từ một nguồn tin cậy, build lại và verify.

### Bài 13. App stdout của lab

Chạy `java -jar build/libs/release-artifact-lab-1.0.0.jar` với project đúng.

**Đáp án:**

~~~text
Artifact smoke test OK
channel=stable
version=1.0.0
~~~

### Bài 14. Code Java chạy trực tiếp

Dùng `javac --release 17`, copy resource vào out và `java -cp out demo.release.Main`. Có kiểm manifest của JAR không?

**Đáp án:** Không. Chỉ kiểm Java source + runtime resource ở classpath; vẫn phải kiểm JAR Gradle thực.

### Bài 15. Test `gradle run`

`gradle run` có tự kiểm JAR manifest không?

**Đáp án:** Không nhất thiết; Application plugin có thể chạy từ runtimeClasspath, không phải chính JAR.

### Bài 16. Boot JAR bị từ chối vì nested JAR

**Đáp án:** Validator thin JAR không phù hợp. Spring Boot JAR thường cần nested JARs theo layout.

### Bài 17. Dependency verification

`verification-metadata.xml` có bảo đảm Main-Class đúng?

**Đáp án:** Không. Nó bảo vệ downloaded artifacts của Gradle; release JAR cần validator riêng.

### Bài 18. POM/Gradle Module Metadata

Maven consumer fail dù multi-project dependency chạy được.

**Đáp án:** Kiểm publication POM/runtime scopes/variants và thử consumer từ staging repository.

### Bài 19. Chỉ có file .asc

Có file chữ ký nhưng chưa xác minh key/trust.

**Đáp án:** Chưa đủ. Xác minh signature trên chính artifact và trusted identity.

### Bài 20. Release pipeline rebuild sau QA

`artifact A` đã pass, publish stage build lại thành `artifact B`.

**Đáp án:** QA áp dụng cho A, không tự áp dụng cho B. Dùng immutable artifact đã kiểm và so SHA-256 trước/sau upload.

## 21. Checklist cuối cùng

| Hạng mục | Tiêu chí phát hành |
| --- | --- |
| Artifact path | Đúng output task/publication |
| Archive format | Đọc được, không hỏng/duplicate/path traversal |
| Identity | group/name/version/classifier/extension đúng |
| Manifest | Main-Class/Implementation-Version đúng khi cần |
| Contents | Class/resource/config/template bắt buộc đầy đủ |
| Bytecode | Phù hợp JVM target và các dependencies |
| Packaging | Thin/fat/Boot/WAR/distribution đúng contract |
| Smoke test | Chạy **file đã package** ở runtime thực tế |
| Dependency graph | Không thiếu runtime libs, publication metadata đúng |
| Licenses/SBOM | Chính sách third-party components đạt |
| Secrets | Không chứa credentials/private keys/test data nhạy cảm |
| Reproducibility | Timestamps/order và inputs được kiểm soát |
| Integrity | SHA-256 của bytes cuối được lưu và xác minh |
| Signing | Chữ ký/trusted identity đúng khi yêu cầu |
| Provenance | Commit/build workflow/artifact liên kết rõ |
| CI gate | QA fail phải ngăn publish |

**Kết luận:** Để phát hành Java/Gradle đáng tin cậy, kiểm tra **artifact thực tế**, không chỉ log `BUILD SUCCESSFUL`. Kết hợp kiểm tra archive entries, manifest, bytecode, resources, runtime dependencies, Maven metadata và smoke test trên đúng JAR/ZIP. Tạo Gradle verification task với input từ `archiveFile`, chặn release khi sai và giữ **cùng bytes từ QA tới publish** bằng SHA-256/signature/provenance theo chính sách.

## 22. Tài liệu chính thức

- [Gradle — Working with Files: Creating and Reproducible Archives](https://docs.gradle.org/current/userguide/working_with_files.html) — Jar/Zip, archive metadata và tính tái lập.
- [Gradle — Jar Task DSL](https://docs.gradle.org/current/dsl/org.gradle.jvm.tasks.Jar.html) — `archiveFile`, manifest và duplicates policy.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html) — `jar`, `processResources`, `check` và Java source sets.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html) — `run`, `installDist`, `distZip` và scripts.
- [Gradle — Implementing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html) — typed task inputs và `@TaskAction`.
- [Gradle — Lazy Configuration](https://docs.gradle.org/current/userguide/lazy_configuration.html) — Provider APIs và implicit task dependencies.
- [Gradle — Maven Publish](https://docs.gradle.org/current/userguide/publishing_maven.html) — publications, POM và Gradle Module Metadata.
- [Gradle — Publishing Setup](https://docs.gradle.org/current/userguide/publishing_setup.html) — artifacts/metadata/repositories.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html) — checksum/signature của downloaded dependencies.
- [Gradle — Signing Plugin](https://docs.gradle.org/current/userguide/signing_plugin.html) — signing publications.
- [Oracle JDK 17 — jar Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html) — list/extract và manifest.
- [Oracle JDK 17 — javap Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html) — kiểm bytecode major và public signatures.
- [JVM Specification — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html) — `CAFEBABE`, minor và major.
- [Reproducible Builds](https://reproducible-builds.org/) — byte-for-byte reproducibility.

# JAR, ZIP, TAR và phân biệt classes với artifact phân phối trong Gradle

## 1. Mục tiêu: biên dịch xong chưa có nghĩa đã có sản phẩm để giao

Khi chạy `./gradlew classes`, Java project có thể đã tạo thành công các file `.class`. Nhưng một thư mục chứa bytecode **không đồng nghĩa** một JAR đã được đóng gói, càng không đồng nghĩa người dùng khác có thể giải nén và chạy ứng dụng đầy đủ trên một máy sạch.

Gradle phân biệt các tầng:

1. **Source**: các file `.java` và resources mà bạn viết.
2. **Compiled outputs**: các file `.class` và resources đã xử lý, thường ở `build/classes/java/main` và `build/resources/main`.
3. **JAR artifact**: một Java archive chứa outputs của source set, thường ở `build/libs/<project>-<version>.jar`.
4. **ZIP/TAR archive**: một container file có thể mang JAR, scripts, tài liệu, cấu hình và runtime dependencies tùy `CopySpec`.
5. **Application distribution**: một **bố cục phân phối có quy tắc** (ví dụ `bin/`, `lib/`, `config/`), có scripts khởi chạy, runtime dependencies và các thành phần cần thiết để chạy ứng dụng.
6. **Publication**: một artifact/module được công bố vào Maven/Ivy repository với tọa độ và metadata để dự án khác resolve. Publication có thể tham chiếu JAR nhưng **không phải** cùng thao tác với tạo ZIP/TAR.

Sau bài học, bạn sẽ:

- Phân biệt chính xác `classes`, `jar`, `assemble`, `build` và `check`.
- Hiểu `Jar`, `Zip`, `Tar` là ba Gradle task types, điểm giống và khác về file format.
- Biết JAR thường chỉ chứa main outputs, **không tự nhúng tất cả runtime dependency JARs**.
- Tạo ví dụ Java 17 + Gradle Kotlin DSL có JAR, custom ZIP, custom TAR.GZ và application distribution.
- Kiểm tra nội dung archive bằng `jar tf`, `unzip -l`, `tar -tf`, không chỉ nhìn tên file.
- Hiểu `application` tự áp dụng `java` và `distribution`, tạo `run`, `startScripts`, `installDist`, `distZip`, `distTar`.
- Chẩn đoán vì sao `java -jar` không chạy được mặc dù `./gradlew run` và generated start scripts chạy đúng.
- Tùy chỉnh archive naming, source sets, copy specifications, duplicate policies, file permissions và reproducibility.
- Chọn đúng artifact để publish library, phân phối ứng dụng, cung cấp sources hoặc triển khai lên máy mới.

**Nguyên tắc:** `classes` tạo **nội dung biên dịch**; `jar` tạo **Java binary artifact**; `distZip`/`distTar` tạo **gói phân phối theo bố cục cụ thể**. Tên đuôi file một mình không nói gói đó đã đủ để chạy.

## 2. Từ source tới classes, JAR và distribution

Một Java application điển hình:

```text
src/main/java/demo/Main.java
src/main/resources/banner.txt
               |
               v
     compileJava / processResources
               |
        +------+------+
        |             |
        v             v
build/classes/      build/resources/
java/main/...       main/banner.txt
        |             |
        +------+------+
               |
               v
         sourceSets.main.output
               |
               +------------------------+
               |                        |
               v                        v
             jar                     run
               |                  (JavaExec với
               |                 runtimeClasspath)
               v
  build/libs/archive-lab-1.0.0.jar
               |
               +----------------------------+
               |                            |
               v                            v
       Custom Zip / Tar               Application plugin
    (nội dung tùy CopySpec)        startScripts + runtime deps
                                            |
                                +-----------+-----------+
                                |           |           |
                                v           v           v
                              distZip     distTar    installDist
                                |           |           |
                                v           v           v
                          .zip archive  .tar archive  directory tree
```

**Đọc chính xác sơ đồ:** `run` sử dụng outputs/classes và runtime dependencies để khởi chạy, nên **không bắt buộc đợi JAR**. Trong khi đó distribution của Application plugin thông thường chứa **JAR đã xây dựng + runtime library JARs + scripts**. Nếu project dùng plugins/variants tùy chỉnh, hãy kiểm tra task graph thực tế.

### 2.1. `classes` là lifecycle task, không phải một format file

Java plugin tạo `compileJava`, `processResources` và `classes`. Task `classes` thường phụ thuộc compile và resources processing:

```text
classes
  ├── compileJava
  └── processResources
```

Các outputs thường có dạng:

```text
build/
├── classes/java/main/demo/Main.class
└── resources/main/banner.txt
```

Đây là **thư mục/đầu ra biên dịch**, không phải một `classes.jar` tên cố định. Đặc biệt:

- `./gradlew clean classes` không cần tạo file `build/libs/*.jar`.
- `classes` không resolve hay copy tất cả runtime JARs vào thư mục output.
- `processResources` có thể thực hiện filtering/copy resources; kết quả không nhất thiết giống nguyên bytes trong `src/main/resources` nếu có rules.
- Thư mục classes có thể được IDE, task `run`, tests hoặc Gradle variant-aware classpath sử dụng trực tiếp.
- Nếu một JAR cũ vẫn nằm ở `build/libs` sau khi chạy `classes`, đừng suy rằng task `classes` tạo nó; hãy chạy `clean classes` trong sandbox để quan sát.

### 2.2. `sourceSets.main.output` là gì?

Với Java plugin, `sourceSets.main.output` là một tập hợp các compiled classes directories và processed resources của source set `main`. Nó được `Jar` mặc định đóng gói; nó **không** phải output archive file. Kotlin DSL có thể truy cập:

```kotlin
val mainOutput = sourceSets.main.get().output
```

Đây là **đoạn lấy một đối tượng SourceSetOutput**, không tự viết ra file khi đặt vào build script. Các task nhận nó làm input sẽ được Gradle nối dependency tới những tasks tạo outputs khi thông tin producer được mô hình hóa đúng.

Khi project dùng generated Java sources, annotations processing hoặc custom resource directories, output có thể gồm nhiều directories. Đừng hardcode chỉ `build/classes/java/main` rồi làm mất processed resources hoặc generated classes.

## 3. Bảng phân biệt JAR, ZIP và TAR

| Định dạng | Gradle task type | Format dữ liệu | Điển hình dùng cho | Có tự bao gồm dependencies? |
| --- | --- | --- | --- | --- |
| **JAR** (`.jar`) | `Jar` | ZIP-compatible archive có conventions Java (`META-INF/MANIFEST.MF`) | Java library/module artifact, classpath | **Không**, trừ khi cấu hình packaging khác |
| **ZIP** (`.zip`) | `Zip` | ZIP archive, thường có nén từng entry | Gói ứng dụng, tài liệu, scripts, assets | **Không tự động** với custom Zip; Application distribution có |
| **TAR** (`.tar`) | `Tar` | TAR container, mặc định không nén | Phân phối dạng Unix, giữ structure/permissions | **Không tự động** với custom Tar; Application distribution có |
| **TAR.GZ** (`.tar.gz`/`.tgz`) | `Tar` + `Compression.GZIP` | TAR container được gzip cả stream | Release bundle nén dạng Unix | Tùy `CopySpec` hoặc distribution |
| **Application distribution** | `distZip`/`distTar`/`installDist` | ZIP/TAR hoặc directory tree | App chạy từ scripts, JARs trong `lib/` | **Có runtime deps** theo Application plugin |

**JAR thực chất dùng cấu trúc ZIP**, nhưng JAR có quy ước Java class loading, manifest và ký JAR. Đổi đuôi `.zip` thành `.jar` **không** tự tạo đúng Java artifact; ngược lại, ZIP chứa JAR chưa chắc có manifest để JVM chạy trực tiếp.

**TAR khác ZIP:** TAR mô tả file tree/metadata, bản thân TAR thường **không nén**; nén gzip là bước riêng. Cả ZIP và TAR có thể dùng trên nhiều hệ điều hành; không có quy tắc “ZIP chỉ dành cho Windows, TAR chỉ dành cho Linux”. Hai gói application mặc định thường mang **cả script Unix và script Windows**.

## 4. `jar` mặc định chứa gì, không chứa gì?

Áp dụng Java plugin:

```kotlin
plugins {
    java
}
```

Gradle tạo task `jar` (type `Jar`), lấy `main` source set outputs và thường tạo `build/libs/<name>-<version>.jar`. Nếu project có `version = "1.0.0"` và tên `archive-lab`, archive mặc định là:

```text
build/libs/archive-lab-1.0.0.jar
```

Nội dung thường là:

```text
META-INF/
META-INF/MANIFEST.MF
demo/Main.class
banner.txt
```

Không có mặc định:

- `src/main/java/demo/Main.java` (source chưa compiled, trừ khi bật sources JAR hoặc custom packaging).
- `src/test/java/...` và test class outputs.
- `build/reports/tests/test`, PMD/SpotBugs/Jacoco reports.
- Tất cả Maven dependencies trong `runtimeClasspath`.
- Bash/Windows start scripts, README, license, config files ngoài source set nếu chưa thêm.
- Các distribution directories `bin/`, `lib/`, `docs/`.

**Dùng `jar tf <file.jar>` kiểm tra, không suy từ tên file.** Nếu có `ClassNotFoundException` hoặc `NoClassDefFoundError` khi `java -jar`, nguyên nhân có thể là runtime dependency thiếu, không phải JAR không có main class.

### 4.1. `Main-Class` của manifest có nghĩa gì?

File `META-INF/MANIFEST.MF` có thể khai báo:

```text
Manifest-Version: 1.0
Main-Class: demo.Main
```

Nó cho JVM biết entry point khi dùng `java -jar`. Nhưng **`Main-Class` không thêm dependency JARs vào cùng archive**. Theo semantics của `java -jar`, JVM dựa vào executable JAR/manifest classpath; tùy ý đặt `-cp` cùng `-jar` không có tác dụng như người học thường nghĩ. Generated application start scripts hoặc custom launcher quản lý classpath rõ ràng hơn.

Nếu không có `Main-Class`, có thể gặp:

```text
no main manifest attribute, in archive-lab-1.0.0.jar
```

Nếu có `Main-Class` nhưng thiếu `commons-lang3`, có thể gặp:

```text
java.lang.NoClassDefFoundError: org/apache/commons/lang3/StringUtils
```

Đây là **các dạng lỗi minh họa**. Vị trí/stack trace sẽ khác theo Java version và code path. Hãy xem dependency graph và nội dung JAR trước khi sửa manifest hoặc cố tạo fat JAR.

## 5. Task lifecycle: `classes`, `jar`, `assemble`, `check`, `build`

| Task | Vai trò | Nội dung tối thiểu điển hình |
| --- | --- | --- |
| `compileJava` | Compile main Java sources | `.class` output |
| `processResources` | Copy/transform main resources | Resources output |
| `classes` | Lifecycle cho compile + resources main | Không tự tạo archive |
| `jar` | Tạo Java archive của main outputs | `build/libs/<name>-<version>.jar` |
| `assemble` | Tập hợp các outputs cần assemble | Với Java: thường jar; với Application: **cả dist archives** |
| `test` | Chạy unit tests trong test worker JVM | Test reports, không tạo JAR phân phối |
| `check` | Chạy verification tasks theo plugin | Test, static analysis, v.v. |
| `build` | Lifecycle tổng hợp | `assemble` + `check` |
| `run` | Khởi động application bằng JavaExec | Runtime classpath trực tiếp, không cần archive |
| `distZip`/`distTar` | Đóng gói distribution chính | ZIP/TAR với scripts và runtime JARs |
| `installDist` | Tạo directory distribution | `build/install/<project>/...` |

**Điểm quan trọng của Application/Distribution plugin:** các task phân phối `distZip`/`distTar` được nối vào `assemble`. Vì vậy `./gradlew assemble` hoặc `./gradlew build` của ứng dụng có thể tạo **JAR lẫn ZIP/TAR**; không phải “assemble chỉ tạo JAR”. Nếu chỉ cần một ZIP, gọi `distZip` trực tiếp để tránh tạo TAR ngoài ý muốn. Nếu chỉ muốn verification mà không xây các distribution archives, có thể chạy `check`.

Trong Java library project **không** áp dụng Distribution/Application plugin, `assemble` thường chỉ kéo task `jar` cùng các archives khác mà build đã cấu hình; không tự phát sinh `distZip`/`distTar`.

## 6. Demo độc lập: một app Java 17 có runtime dependency

Ví dụ sử dụng **Gradle Kotlin DSL**, Application plugin (tự áp dụng Java và Distribution), Java 17, một dependency ngoài là Apache Commons Lang 3. Các bước sẽ cho thấy:

- `classes` chỉ tạo compiled outputs/resources.
- `jar` tạo Java artifact có manifest, nhưng vẫn cần Commons Lang.
- `run` và generated distribution scripts hoạt động vì runtime classpath đầy đủ.
- `distZip`/`distTar` cung cấp runtime dependencies và scripts.
- Custom `artifactZip`/`artifactTarGz` chỉ chứa nội dung do ta khai báo, **không tự thành complete distribution**.

Điều kiện để chạy: **JDK 17**, Gradle Wrapper tương thích JDK 17, và truy cập Maven Central khi chưa có dependency trong cache.

### 6.1. Cấu trúc thư mục

```text
archive-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── README.md
├── src/
│   ├── main/
│   │   ├── java/demo/Main.java
│   │   └── resources/banner.txt
│   └── dist/
│       └── config/app.properties
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
```

Đây là **một Gradle project**, không phải multi-project. File `src/dist/config/app.properties` được Application/Distribution plugin đưa vào distribution root theo convention, **không phải resource của main classpath**.

`settings.gradle.kts`:

```kotlin
rootProject.name = "archive-lab"
```

`README.md`:

```markdown
# Archive Lab

Run the generated script in bin/ after installing or extracting the distribution.
The application's JAR and runtime dependency JARs are under lib/.
```

`src/main/resources/banner.txt` (một dòng, kết thúc newline):

```text
RESOURCE_OK
```

`src/dist/config/app.properties`:

```properties
mode=demo
```

App trong ví dụ **không tự đọc** file `app.properties`; nó chỉ minh họa một cấu hình ngoài JAR được đóng gói vào phân phối. Dự án production cần định nghĩa đường load config, secrets và precedence cụ thể.

### 6.2. Java source `src/main/java/demo/Main.java`

```java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.apache.commons.lang3.StringUtils;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws IOException {
        String greeting = StringUtils.capitalize("hello from gradle");

        try (InputStream input = Main.class.getResourceAsStream("/banner.txt")) {
            if (input == null) {
                throw new IllegalStateException("banner.txt not on classpath");
            }
            System.out.print(new String(input.readAllBytes(), StandardCharsets.UTF_8));
        }

        System.out.println(greeting);
    }
}
```

Code dựa vào:

- `banner.txt` là **processed resource** từ source set `main`, có trong JAR/classpath.
- `StringUtils` thuộc **Apache Commons Lang 3**, không thuộc JDK 17. Gradle phải cấp dependency trên `compileClasspath` và `runtimeClasspath`.
- `getResourceAsStream("/banner.txt")` đọc resource từ classpath, không từ filesystem path cố định của máy.
- `readAllBytes()` có từ Java 9; với toolchain 17 hợp lệ.
- `StringUtils.capitalize("hello from gradle")` trả chuỗi `Hello from gradle`.

Khi classpath đầy đủ và resource đúng, stdout ứng dụng **chính xác hai dòng**:

```text
RESOURCE_OK
Hello from gradle
```

Đây chỉ là **stdout từ chương trình Java**; Gradle còn có thể in task statuses, warnings hay download progress nếu không dùng chế độ quiet.

### 6.3. Toàn bộ `build.gradle.kts`

```kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask
import org.gradle.api.tasks.bundling.Compression
import org.gradle.api.tasks.bundling.Tar
import org.gradle.api.tasks.bundling.Zip
import org.gradle.jvm.tasks.Jar

plugins {
    application
}

group = "com.example"
version = "1.0.0"

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}

application {
    mainClass.set("demo.Main")
}

// jar là Java artifact: Main-Class chỉ định entry point,
// KHÔNG tự nhúng Commons Lang vào jar này.
tasks.named<Jar>("jar") {
    manifest {
        attributes["Main-Class"] = "demo.Main"
    }
}

// Thêm tài liệu vào main application distribution.
// src/dist/ được thêm theo convention của distribution plugin.
distributions {
    main {
        contents {
            from("README.md") {
                into("docs")
            }
        }
    }
}

// Nêu rõ reproducibility policy khi dự án còn hỗ trợ
// Gradle cũ hơn 9.0. Gradle 9+ mặc định đã dùng hai giá trị này.
tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}

// Hai archive tùy chỉnh: chỉ có jar + README, không có
// start scripts hoặc Commons Lang runtime JAR.
tasks.register<Zip>("artifactZip") {
    archiveBaseName.set("archive-lab")
    archiveVersion.set("1.0.0")
    archiveClassifier.set("artifact-only")
    destinationDirectory.set(layout.buildDirectory.dir("packages"))

    from(tasks.named<Jar>("jar")) {
        into("lib")
    }
    from("README.md") {
        into("docs")
    }
}

tasks.register<Tar>("artifactTarGz") {
    archiveBaseName.set("archive-lab")
    archiveVersion.set("1.0.0")
    archiveClassifier.set("artifact-only")
    archiveExtension.set("tar.gz")
    destinationDirectory.set(layout.buildDirectory.dir("packages"))
    compression = Compression.GZIP

    from(tasks.named<Jar>("jar")) {
        into("lib")
    }
    from("README.md") {
        into("docs")
    }
}
```

**Các điểm cần kiểm tra kỹ:**

1. `application` là **Gradle core plugin**; nó tự áp dụng Java và Distribution plugins. Không cần khai báo `java` và `distribution` lần thứ hai.
2. `group` là tọa độ dùng cho module publication; nó **không làm thay đổi đường archive mặc định** khi base name/version đã được cấu hình.
3. `version="1.0.0"` làm JAR có suffix version và default distribution archives cũng dùng version này.
4. `java.toolchain` chọn compiler Java 17; không buộc JVM đang chạy Gradle Daemon cũng phải bằng 17.
5. `application.mainClass` chỉ main entry point cho `run`/generated scripts. `jar.manifest` được cấu hình riêng để cho phép thử `java -jar`.
6. `distributions.main.contents` bổ sung `README.md` vào `docs/` trong **distribution**, không tự đưa README vào JAR.
7. `src/dist/` được thêm theo convention Application/Distribution plugin vào root distribution, nên `config/app.properties` xuất hiện trong ZIP/TAR/installDist.
8. `AbstractArchiveTask` config ảnh hưởng `Jar`/`Zip`/`Tar`. Gradle 9.0+ đã reproducible by default về thứ tự file/timestamps/permissions; đặt rõ hai flags có ích nếu còn dùng Gradle 8.x.
9. `from(tasks.named<Jar>("jar"))` nhận **task provider** làm source, nên Gradle biết `artifactZip`/`artifactTarGz` cần output của `jar`. Đừng trỏ bằng string path tới một file chưa tồn tại rồi cho rằng task producer sẽ tự chạy.
10. Custom ZIP/TAR.GZ chỉ chứa **JAR + README**, không có classpath libs và launch scripts; nó là **gói archive tùy chỉnh**, không phải application distribution hoàn chỉnh.
11. `archiveExtension.set("tar.gz")` chỉ định đúng đuôi file, `compression = Compression.GZIP` thực sự bật nén gzip. Đổi tên `.tar` thành `.tar.gz` mà không bật compression là sai.
12. Custom archives đi vào `build/packages/`; Application distribution mặc định đi vào `build/distributions/`. Tránh ghi hai task cùng output path/name.

### 6.4. Chạy từng pha đúng thứ tự

Trên Linux/macOS:

```bash
./gradlew --version
./gradlew clean classes
./gradlew jar
./gradlew -q run
./gradlew distZip distTar installDist
./gradlew artifactZip artifactTarGz
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat clean classes
.\gradlew.bat jar
.\gradlew.bat -q run
.\gradlew.bat distZip distTar installDist
.\gradlew.bat artifactZip artifactTarGz
```

**Sau `clean classes`:** có main classes/resources, chưa cần JAR. **Sau `jar`:** có `build/libs/archive-lab-1.0.0.jar`. **Sau `run`:** app chạy qua classpath có Commons Lang, in đúng `RESOURCE_OK` và `Hello from gradle`. **Sau distribution tasks:** có file ZIP/TAR và install directory. **Sau custom tasks:** có ZIP/TAR.GZ chỉ chứa JAR và README.

Nếu Gradle Wrapper chưa tồn tại trong một thư mục mới hoàn toàn, cần dùng Gradle cài tạm để tạo Wrapper rồi dùng các lệnh trên. Nếu CI chưa có JDK 17 và không cấu hình toolchain download resolver, build có thể fail trước bước package — không suy rằng source/JAR sai.

### 6.5. Đường output mong đợi

```text
build/
├── classes/java/main/demo/Main.class
├── resources/main/banner.txt
├── libs/archive-lab-1.0.0.jar
├── distributions/
│   ├── archive-lab-1.0.0.zip
│   └── archive-lab-1.0.0.tar
├── install/archive-lab/
│   ├── bin/
│   │   ├── archive-lab
│   │   └── archive-lab.bat
│   ├── lib/
│   │   ├── archive-lab-1.0.0.jar
│   │   └── commons-lang3-3.14.0.jar
│   ├── config/app.properties
│   └── docs/README.md
└── packages/
    ├── archive-lab-1.0.0-artifact-only.zip
    └── archive-lab-1.0.0-artifact-only.tar.gz
```

Đây là **cấu trúc đầu ra dự kiến theo các task/conventions của demo**, không phải một log đã chạy trên mọi Gradle version. Các file trong `build/distributions` có **thư mục root bên trong archive** tên tương ứng `archive-lab-1.0.0/`. Tên file runtime dependency/version phụ thuộc đúng dependency Gradle chọn. Nếu bạn đổi `archiveBaseName`, `applicationName`, `version` hoặc distributions name, các paths sẽ thay đổi.

### 6.6. Kiểm tra JAR bằng JDK

```bash
jar tf build/libs/archive-lab-1.0.0.jar
```

Các entry quan trọng mong đợi:

```text
META-INF/
META-INF/MANIFEST.MF
demo/Main.class
banner.txt
```

Lệnh `jar tf` có thể in thêm thứ tự directories/entries khác. Quan trọng là **class và resource hiện diện**, chứ không phải thứ tự trình bày. Bạn cũng có thể đọc manifest sau khi unzip, ví dụ `unzip -p build/libs/archive-lab-1.0.0.jar META-INF/MANIFEST.MF` nếu có công cụ `unzip`.

Không nên dùng `jar tf build/classes/java/main`: `jar tf` đọc archive file, không đọc một directory theo kiểu liệt kê nội dung classes. Đối với compiled output directory, dùng `find` hoặc `Get-ChildItem`.

### 6.7. Thử `java -jar` để hiểu dependency thiếu

Vì build script đã cấu hình `Main-Class`, bạn có thể thử:

```bash
java -jar build/libs/archive-lab-1.0.0.jar
```

**Dự kiến FAIL** do `org.apache.commons.lang3.StringUtils` không nằm trong plain JAR và manifest không khai báo external classpath. Nguyên nhân gốc điển hình:

```text
java.lang.NoClassDefFoundError: org/apache/commons/lang3/StringUtils
```

Điều này **không có nghĩa `jar` đóng gói sai**. Nó đóng gói đúng loại Java artifact mặc định; bạn đang dùng **sai mô hình khởi chạy** cho ứng dụng có runtime dependencies.

Không khắc phục bằng cách đổi tên ZIP thành JAR hay nhét bừa toàn bộ `runtimeClasspath` vào JAR. Khi cần app chạy độc lập, hãy dùng application distribution/start scripts hoặc một packaging strategy cụ thể như Shadow fat JAR với dependency/resource merge, license và duplicate policies rõ ràng.

### 6.8. Chạy application distribution đã install

Linux/macOS:

```bash
./build/install/archive-lab/bin/archive-lab
```

Windows PowerShell:

```powershell
.\build\install\archive-lab\bin\archive-lab.bat
```

Khi Java runtime tương thích có sẵn, scripts được Application plugin tạo sẽ đặt classpath gồm `lib/archive-lab-1.0.0.jar` **và** `lib/commons-lang3-3.14.0.jar`; output ứng dụng:

```text
RESOURCE_OK
Hello from gradle
```

Điều kiện **máy đích vẫn cần Java runtime** phù hợp, trừ khi bạn còn đóng gói runtime image bằng `jlink`/`jpackage` hoặc công cụ khác. Application distribution mặc định **không mang một JRE riêng**. Đừng quảng cáo ZIP/TAR này là native executable không cần Java.

### 6.9. Kiểm tra ZIP và TAR bằng công cụ hệ điều hành

Linux/macOS:

```bash
unzip -l build/distributions/archive-lab-1.0.0.zip
tar -tf build/distributions/archive-lab-1.0.0.tar

unzip -l build/packages/archive-lab-1.0.0-artifact-only.zip
tar -tzf build/packages/archive-lab-1.0.0-artifact-only.tar.gz
```

PowerShell có thể xem ZIP bằng `tar -tf` trên môi trường có bsdtar hỗ trợ ZIP, hoặc dùng `Expand-Archive` vào một **sandbox directory**. Để xem JAR mà không dùng `unzip`, dùng `jar tf` từ JDK. Windows `tar.exe` có mặt trên nhiều môi trường nhưng không phải mọi bản Windows cũ; nếu thiếu thì cài công cụ TAR tương thích.

**Kỳ vọng so sánh:**

- `distZip`/`distTar`: có `bin/` launcher scripts và `lib/` chứa app + Commons Lang JAR, `config/`, `docs/`.
- `artifactZip`/`artifactTarGz`: chỉ có `lib/archive-lab-1.0.0.jar` và `docs/README.md`; **không có Commons Lang và scripts**.
- `jar`: có `demo/Main.class` và `banner.txt` trong archive, không có toàn bộ hierarchy distribution.
- `classes`: directory outputs, không có ZIP/TAR.

Chính **nội dung** mới xác định liệu archive dùng cho người chạy, cho lập trình viên tiêu thụ thư viện, hay chỉ là bản đóng gói thủ công.

## 7. Vì sao `distZip`/`distTar` giải quyết được vấn đề runtime classpath?

Application plugin tự tạo **main distribution** với layout thường thấy:

```text
archive-lab-1.0.0/
├── bin/
│   ├── archive-lab
│   └── archive-lab.bat
├── lib/
│   ├── archive-lab-1.0.0.jar
│   └── commons-lang3-3.14.0.jar
├── config/app.properties
└── docs/README.md
```

- `bin/` gồm OS-specific start scripts được task `startScripts` tạo.
- `lib/` gồm app JAR và **all runtime dependencies** theo `runtimeClasspath` của application.
- `src/dist` thêm files tùy chọn vào distribution root.
- `distributions.main.contents` thêm custom documents hoặc configs theo `CopySpec`.
- `distZip` tạo ZIP của layout, `distTar` tạo TAR của layout, `installDist` tạo filesystem tree cùng mục đích.
- `assembleDist` là lifecycle task gọi cả `distZip` và `distTar`.
- `assemble`/`build` cũng có thể tạo distribution archives do plugin wiring.

**Không nhầm:** default `distTar` của Distribution plugin là **TAR thường** với đuôi `.tar`, không phải TAR.GZ mặc định. Muốn tarball gzip, phải điều chỉnh `compression`/`archiveExtension` cho task phù hợp hoặc tạo custom Tar như demo.

**Khi không muốn ship mọi runtime dependency:** bạn phải thiết kế distribution layout/launch strategy khác và chứng minh classpath vẫn đúng. Xóa bớt JAR khỏi `lib` để giảm dung lượng có thể gây `ClassNotFoundException` khi chạy trên máy sạch.

## 8. JAR cho thư viện và distribution cho ứng dụng là hai hợp đồng khác nhau

### 8.1. Java library cho developer khác dùng qua Maven/Ivy

Với module thư viện:

```kotlin
plugins {
    `java-library`
    `maven-publish`
}
```

`jar` tạo binary library JAR; `maven-publish` có thể công bố cùng POM/Gradle Module Metadata, group/name/version, API/runtime dependencies và variants. **Một JAR file trần không mô tả đầy đủ dependencies bắc cầu** khi consumer chỉ chép file thủ công.

Để thêm source JAR/Javadoc JAR:

```kotlin
java {
    withSourcesJar()
    withJavadocJar()
}
```

Những calls này tạo các task `sourcesJar` và `javadocJar` cùng outgoing variants/publication khi plugin hỗ trợ. **Sources JAR** chứa source files cho IDE/developer, **không phải** compiled classes dùng để chạy app. **Javadoc JAR** chứa documentation, không phải runtime JAR.

Đây là **một phương án cho library project**, không thay thế nguyên build script Application demo nếu bạn muốn code vẫn chạy bằng `run`/`distZip`. Library artifact distribution có thể dùng plugin `java-library-distribution` khi cần gói ZIP gồm library và runtime deps cho offline consumption, nhưng nó khác application distribution có start scripts.

### 8.2. Ứng dụng để người dùng chạy trên máy sạch

Với application cần launch scripts và classpath:

```kotlin
plugins {
    application
}

application {
    mainClass.set("demo.Main")
}
```

Đây là **mẫu tối thiểu về launcher**; cần source/dependencies/repositories như demo để chạy thật. Nếu app còn database config, template, SQL migrations, native libs hoặc user docs, thêm chúng vào distribution có đường dẫn và quyền truy cập rõ ràng.

Một ứng dụng server có thể dùng Docker/OCI image, `jlink` runtime image hoặc `jpackage` installer thay ZIP/TAR truyền thống. Không có lựa chọn đúng tuyệt đối; chọn format theo **consumer của artifact**: developer resolve Maven module, server deploy OCI image, ops tải TAR.GZ, end user dùng installer, CI lưu debug ZIP.

## 9. Tùy chỉnh `Jar` mà không phá output mặc định

Ví dụ thay **tên classifier** cho một JAR bổ sung, không sửa `jar` mặc định:

```kotlin
tasks.register<Jar>("diagnosticsJar") {
    archiveClassifier.set("diagnostics")
    destinationDirectory.set(layout.buildDirectory.dir("libs"))

    from(sourceSets.main.get().output)
}
```

Khi có `project.name=archive-lab` và `version=1.0.0`, task này tạo:

```text
build/libs/archive-lab-1.0.0-diagnostics.jar
```

**Lưu ý:** đây chỉ là **thêm một JAR chứa main output**, chưa hề có special diagnostics files nếu không thêm chúng. Có thể cần task producer relationships cho files được sinh riêng. Khi dùng source set output đúng Gradle model, Gradle có thể nối producer tasks; khi chỉ dùng path string đến file do task khác tạo ra, hãy đưa `TaskProvider`/Provider output vào `from(...)` hoặc `builtBy`.

### 9.1. Thay tên archive bằng thuộc tính nào?

```kotlin
tasks.named<Jar>("jar") {
    archiveBaseName.set("my-library")
    archiveVersion.set("2.0.0")
    archiveClassifier.set("plain")
    archiveExtension.set("jar")
}
```

Ví dụ task JAR sẽ có tên theo convention:

```text
my-library-2.0.0-plain.jar
```

Đây là **đoạn thay thế riêng** để học archive naming. Đừng dán vào Application demo rồi vẫn mong tên `archive-lab-1.0.0.jar` trong distribution/output/commands không đổi. Plugin publication và generated start scripts có thể cần đồng bộ nếu tùy chỉnh classifier/name.

Các thuộc tính của `AbstractArchiveTask`:

| Property | Vai trò | Ví dụ |
| --- | --- | --- |
| `archiveBaseName` | Phần base của tên | `archive-lab` |
| `archiveAppendix` | Phần mô tả thêm trước version | `cli` |
| `archiveVersion` | Version trong filename | `1.0.0` |
| `archiveClassifier` | Phân biệt artifact variant | `sources`, `plain`, `all` |
| `archiveExtension` | Đuôi file, phải phù hợp bytes thực | `jar`, `zip`, `tar`, `tar.gz` |
| `archiveFileName` | Override toàn bộ tên | `release.zip` |
| `destinationDirectory` | Thư mục output | `build/libs`, `build/distributions` |
| `archiveFile` | Provider đường dẫn output đầy đủ | Task/CopySpec khác có thể dùng |

Không hardcode `build/libs/lib.jar` trong task tiêu thụ nếu task producer đã có `archiveFile` provider. Sử dụng provider giúp Gradle biết producer task dependencies, chống mismatch khi version/classifier đổi.

### 9.2. `META-INF/MANIFEST.MF` và multi-release JAR

JAR manifest có thể chứa `Implementation-Title`, `Implementation-Version`, `Automatic-Module-Name`, `Main-Class` hoặc `Multi-Release: true` theo nhu cầu.

- `Main-Class` chỉ executable entry point.
- `Automatic-Module-Name` hỗ trợ JPMS naming cho automatic module; không tạo module descriptor Java tự động.
- Multi-release JAR dùng `META-INF/versions/<N>/...` theo quy tắc JVM và cần build/test bytecode variants phù hợp; chỉ thêm manifest `Multi-Release: true` mà không có layout đúng là cấu hình vô ích.
- Manifest attributes không tự thay thế Maven POM/Gradle Module Metadata.
- Nếu dùng signing JAR, checksum/signature quy trình khác với việc gắn vài key/value vào manifest.

Chỉ đưa các manifest entries phục vụ hợp đồng thật của artifact; không “nhét nhiều metadata hơn cho chắc”.

## 10. Tùy chỉnh ZIP/TAR bằng `CopySpec`

`Jar`, `Zip`, `Tar` cùng chia sẻ phần lớn cơ chế **CopySpec**:

- `from(...)`: file tree/TaskProvider nguồn.
- `into(...)`: đường tương đối bên trong archive.
- `include(...)`, `exclude(...)`: lọc files.
- `rename(...)`, `eachFile(...)`: đổi đường/tên theo policy.
- `duplicatesStrategy`: cách xử lý nhiều source cùng internal archive path.
- `filePermissions`/`dirPermissions`: quyền của entries nếu format/tool hỗ trợ.

Ví dụ ZIP chỉ nhận docs và một script:

```kotlin
tasks.register<Zip>("docsZip") {
    archiveClassifier.set("docs")
    destinationDirectory.set(layout.buildDirectory.dir("packages"))

    from("README.md") {
        into("docs")
    }
    from("scripts") {
        include("*.sh")
        into("bin")
    }
}
```

**Mẫu này chưa độc lập nếu không có thư mục `scripts`**; khi thư mục không tồn tại hoặc không match, phần scripts có thể rỗng. Nó không tự sinh launchers như Application plugin. Cần phân biệt nguồn copy được khai báo và sản phẩm thực sự đã tạo.

### 10.1. Hai source có cùng đường bên trong archive

Ví dụ:

```text
folderA/config.yml
folderB/config.yml
```

Nếu cả hai được `from(...)` vào archive root, sẽ trùng `config.yml`. Các chiến lược phổ biến:

| `DuplicatesStrategy` | Hiệu ứng |
| --- | --- |
| `FAIL` | Fail task, buộc sửa xung đột |
| `EXCLUDE` | Bỏ qua bản trùng sau, cần biết thứ tự |
| `INCLUDE` | Có thể tạo nhiều entries cùng path, behavior đọc archive có thể khó dự đoán |
| `WARN` | Cho phép nhưng cảnh báo |
| `INHERIT` | Theo parent CopySpec hoặc task policy |

Đối với distribution có thể được giải nén/triển khai, `FAIL` thường là lựa chọn tốt nếu chưa có lý do giữ duplicates:

```kotlin
import org.gradle.api.file.DuplicatesStrategy

tasks.named<Zip>("artifactZip") {
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
```

Đây là **đoạn bổ sung vào demo**. Không đặt `EXCLUDE` vô điều kiện vì có thể vô tình xóa một config/service descriptor quan trọng. Với fat JAR, các entry như `META-INF/services/*` có thể cần **merge đúng semantics** thay vì chọn một bản tùy ý.

### 10.2. Lọc file và đường nội bộ

```kotlin
tasks.named<Zip>("artifactZip") {
    from("docs") {
        include("**/*.md")
        exclude("private/**")
        into("manual")
    }
}
```

Đây là **mẫu thêm nếu dự án có `docs/`**; không phải phần của demo nếu `docs` chưa có. CopySpec paths là paths **bên trong archive**, không tự tạo thư mục tương ứng bên ngoài. Khi đặt `into("lib")` cho JAR, file sẽ nằm dưới `lib/` trong ZIP, nhưng không đổi bản gốc ở `build/libs`.

## 11. TAR thường, TAR.GZ và quyền thực thi scripts

`Tar` của Gradle có thuộc tính `compression`, ví dụ:

```kotlin
import org.gradle.api.tasks.bundling.Compression
import org.gradle.api.tasks.bundling.Tar

tasks.register<Tar>("myCompressedTar") {
    archiveFileName.set("custom-bundle.tar.gz")
    destinationDirectory.set(layout.buildDirectory.dir("packages"))
    compression = Compression.GZIP
    from("src/dist")
}
```

Đoạn này giả định `src/dist` tồn tại, như demo phần 6. Nếu dự án không có file, archive có thể rỗng. Cần đặt **cả compression thực và extension đúng** để công cụ giải nén xác định đúng format.

Lệnh xem:

```bash
tar -tf build/distributions/archive-lab-1.0.0.tar
tar -tzf build/packages/archive-lab-1.0.0-artifact-only.tar.gz
```

- `tar -tf` cho TAR thường.
- `tar -tzf` cho TAR.GZ.
- Một số `tar` tự đoán gzip theo signature/extension, nhưng khi viết tài liệu triển khai nên ghi lệnh rõ.
- ZIP nén theo entry; TAR + gzip nén toàn stream; chiến lược đọc/tải ngẫu nhiên khác nhau.
- TAR lưu permissions/ownership theo format; khi deploy trên Unix, cần giữ hoặc thiết lập executable bits đúng cho scripts.
- ZIP cũng có thể mang permission metadata tùy tool, nhưng không phải công cụ giải nén nào cũng giữ đúng trên mọi hệ điều hành.

**Gradle 9+ reproducible archive defaults và file permissions** cần được hiểu cẩn thận: fixed permissions mặc định (`0644` files, `0755` directories) có thể ảnh hưởng script files trong custom archives. Application plugin có logic distributions/start scripts phù hợp, nhưng với custom `Tar`/`Zip` chứa `.sh` do bạn copy, phải **thiết lập executable bits riêng khi cần**; không giả định chỉ vì tên file kết thúc `.sh` thì nó được chạy bằng `./script.sh` sau giải nén.

## 12. Tính tái lập (reproducibility) của archives

Một archive có cùng nội dung logic nhưng SHA-256 khác giữa hai lần build có thể do:

- File entries được duyệt theo thứ tự filesystem khác nhau.
- Mỗi entry ghi timestamp hiện tại.
- Permissions, owner hoặc metadata hệ điều hành khác nhau.
- File được generate có timestamp, path máy, hostname, build number hoặc random ID.
- Các dependencies từ dynamic/changing versions được resolve ra bytes khác.
- JDK compiler/toolchain, Gradle version, plugin version hoặc line endings khác nhau.
- Compression tool/level hoặc manifest metadata khác nhau.

Từ **Gradle 9.0**, các `AbstractArchiveTask` (`Jar`/`Zip`/`Tar`/...) mặc định dùng thứ tự file ổn định, timestamp cố định và permissions mặc định ổn định. Với dự án hỗ trợ Gradle cũ hơn, có thể ghi rõ:

```kotlin
tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
```

**Điều này giúp nhưng không bảo đảm byte-for-byte reproducibility của toàn build.** Nếu Java bytecode khác, dependency JAR khác hoặc script chứa path/timestamp, archive bytes vẫn khác. Dùng Gradle Wrapper và Java toolchains nhất quán, pin versions/dependency locking, dependency verification và kiểm soát generated files.

### 12.1. Đo SHA-256, không so bằng kích thước file

Linux/macOS:

```bash
sha256sum build/libs/archive-lab-1.0.0.jar
sha256sum build/distributions/archive-lab-1.0.0.zip
```

PowerShell:

```powershell
Get-FileHash build\libs\archive-lab-1.0.0.jar -Algorithm SHA256
Get-FileHash build\distributions\archive-lab-1.0.0.zip -Algorithm SHA256
```

Chạy trên hai clean runners có cùng Gradle/JDK/dependencies và so digest của từng **đúng file**. File size giống nhau không đảm bảo bytes giống nhau. Nếu hashes khác, kiểm tra `jar tf`/`unzip -l` cùng archive entry metadata, rồi so từng output để tìm nguyên nhân trước khi bỏ reproducibility flags.

### 12.2. Không bật mọi flag để “sửa checksum”

Nếu `isPreserveFileTimestamps=true` hoặc `isReproducibleFileOrder=false`, reproducibility giảm; đừng bật lại chỉ để giữ timestamp/permissions giống source. Cần chứng minh chức năng yêu cầu metadata đó và ghi ngoại lệ.

Khi phải bảo tồn quyền thực thi, có thể đặt permissions có chủ đích cho specific entries thay vì dùng mọi permission từ host filesystem. Với custom archive cho release, nên test **giải nén và chạy thật trên target OS**.

## 13. Artifact đã tạo khác artifact đã được publish

`./gradlew jar` tạo file ở local build directory, **không** tự đẩy lên Maven Central, Artifactory hay Nexus. Để một Gradle/Maven project khác tiêu thụ theo GAV, cần publishing:

```kotlin
plugins {
    `java-library`
    `maven-publish`
}

group = "com.example"
version = "1.0.0"

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }
}
```

Đây là **mẫu library publication**, không thể copy riêng vào Application demo mà không hiểu scope/Gradle components và repository credentials. Trong build thật còn cần `repositories` trong `publishing`, policies, POM/Gradle Module Metadata và release versioning.

**Sự phân biệt:**

- `jar`: tạo **artifact bytes**.
- `maven-publish`: tạo/đẩy **publication metadata và artifacts** theo GAV, tùy target task (ví dụ `publishToMavenLocal` hoặc `publish`).
- `distZip`/`distTar`: tạo **archive để phân phối** cho người chạy/ops, không mặc định là Maven publication.
- `withSourcesJar()`/`withJavadocJar()`: thêm **documentation/source variants**, không làm plain jar thành full application distribution.

Nếu công ty publish một ZIP/TAR như artifact Maven đặc biệt, cần chỉ rõ type/classifier và cách downstream consumer sử dụng; đừng tự giả định `implementation("group:name:version")` sẽ tải ZIP thay vì library variant JAR.

## 14. Fat JAR, shaded JAR và Spring Boot executable JAR: đừng nhầm với plain JAR

Khi muốn một file chạy bằng:

```bash
java -jar app-all.jar
```

một cách phổ biến là tạo **fat/uber JAR** gồm app classes và dependencies. Tuy nhiên đây **không phải default `jar`**:

- **Shadow plugin** hoặc công cụ tương đương có thể merge dependency JAR contents vào một JAR.
- **Spring Boot `bootJar`** có layout/classloader riêng, không giống plain JAR `jar`.
- Một số Java modules cần native libraries, agents, security configuration hoặc external files, nên ngay cả fat JAR cũng chưa chắc đủ triển khai.
- Shading/relocation có thể làm đổi package names, reflection, service loader và license notices.
- Duplicate resources như `META-INF/services/*`, signatures của dependency JARs và multi-release entries cần xử lý đúng.
- Các thư viện có licensing restrictions không nên bị bundle tùy tiện.

**Không “tự làm fat JAR” bằng cách**:

```kotlin
// Anti-pattern minh họa; không dùng mù trong production.
tasks.named<Jar>("jar") {
    from(configurations.runtimeClasspath.get().map { zipTree(it) })
}
```

Đoạn này không đảm bảo runtimeClasspath chỉ có JAR, có thể resolve eager trong configuration, xử lý duplicate resources/signatures sai, và phá metadata/relocation. Nó cũng không tự quản lý module descriptors hay transitive licensing. Nếu cần một executable JAR, chọn plugin chuyên dụng có release/compatibility rõ và test output được tạo.

**Quy tắc chọn:** nếu chỉ cần ship app JVM trên máy đã có Java, Application distribution với `bin/` + `lib/` rất dễ kiểm tra. Nếu cần single-file command và packaging đặc thù, fat JAR có thể phù hợp nhưng đòi quy trình kiểm chứng riêng.

## 15. Kiểm tra artifact trước khi giao cho người khác

Một checklist kỹ thuật cho release package:

1. **Đúng version/name?** `archive-lab-1.0.0.zip` có đúng `project.version`? Không dùng `unspecified` tình cờ.
2. **Đúng nội dung?** Dùng `jar tf`, `unzip -l`, `tar -tf` để xem có class/resource/libs/scripts/docs không.
3. **Đúng launcher?** Generated `bin/archive-lab` và `bin/archive-lab.bat` chạy từ install/extracted distribution?
4. **Đúng runtime deps?** `commons-lang3-3.14.0.jar` được copy vào `lib/`, không chỉ tồn tại trong Gradle cache?
5. **Đúng Java version?** Bytecode/JDK toolchain và target runtime có tương thích không?
6. **Đúng permissions?** POSIX start script có executable bit ở môi trường triển khai hoặc có cách chạy bằng `sh`/`bash`?
7. **Không lộ secrets?** Archive không chứa `.env`, `gradle.properties` user-home, access tokens, private keys hoặc debug dumps.
8. **Không trùng entries?** Duplicate paths/resources được xử lý có chủ đích.
9. **Không đường dẫn tuyệt đối của developer?** Tránh archive chứa `/Users/alice/...`, `C:\Users\...` hoặc generated scripts hardcode máy phát triển.
10. **Kết quả có tái lập?** Kiểm reproducible build flags, stable dependencies, checksum.
11. **Có license/notices?** Nếu bundle third-party runtime JARs, tuân thủ license/notices theo chính sách.
12. **Có provenance/signature?** Ghi SHA-256, ký/attest release artifacts khi pipeline yêu cầu.
13. **Có clean-machine smoke test?** Giải nén release archive vào directory mới và chạy launcher, không dựa vào project build outputs/Gradle cache.
14. **Đúng contract consumer?** Nếu artifact là library, kiểm downstream Maven/Gradle consumer; nếu là application, kiểm start scripts.

**Quan trọng:** ZIP/TAR là một format vận chuyển, **không phải bằng chứng bảo mật**. Khi giải nén archives không tin cậy, tránh Zip Slip/path traversal, symlink và ghi đè file ngoài sandbox. Chỉ giải nén artifacts từ nguồn tin cậy bằng công cụ phù hợp.

## 16. Gỡ lỗi theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách chẩn đoán/sửa |
| --- | --- | --- |
| `./gradlew classes` pass nhưng `build/libs` chưa có JAR | `classes` không đóng gói archive | Chạy `jar` hoặc `assemble` |
| `jar` tạo JAR nhưng `java -jar` báo no main manifest | Chưa có `Main-Class` | Cấu hình manifest hoặc dùng launcher đúng |
| Có `Main-Class` nhưng `NoClassDefFoundError` | Runtime dependencies không nằm trong plain JAR | Dùng `run`/Application distribution hoặc packaging classpath đúng |
| `./gradlew run` pass, `java -jar` fail | `run` dùng runtimeClasspath, plain JAR không tự bundle | Đây là khác biệt bình thường, không phải bug `run` |
| `distZip` task không tồn tại | Chưa áp dụng `distribution`/`application` | Apply plugin đúng và xem tasks |
| `installDist` không tạo JAR mới ngoài `lib` | Nó tạo directory tree, không output archive ZIP | Kiểm `build/install/<project>` |
| `distTar` ra `.tar` không phải `.tar.gz` | Default TAR không nén gzip | Cấu hình `compression=GZIP` và extension hoặc dùng custom task |
| ZIP có JAR nhưng không chạy trên máy sạch | Thiếu runtime deps/start scripts/Java | Dùng Application distribution và smoke test |
| `archiveFileName` đúng nhưng `tar -tzf` fail | Bytes thực không gzip, chỉ đổi tên | Bật `Compression.GZIP` |
| Custom `artifactZip` không xuất hiện sau `assemble` | Custom task chưa nối vào lifecycle | Gọi task trực tiếp hoặc `assemble.dependsOn(artifactZip)` |
| `distZip` bị tạo khi chạy `assemble` dù không muốn | Distribution plugin wire dist archives vào `assemble` | Gọi `jar` nếu chỉ cần JAR; `check` nếu chỉ cần verification |
| Compile task UP-TO-DATE nhưng JAR không đổi | `jar` có inputs/outputs và cache riêng | Xem task outcomes, `--rerun-tasks` khi kiểm chứng |
| JAR không có `banner.txt` | Resource path sai hoặc processResources không chạy/filtered | Xem `src/main/resources`, `build/resources/main` và `jar tf` |
| JAR bị nhét cả test classes | Custom `from(sourceSets.test.output)` hoặc packaging sai | Chỉ bundle `sourceSets.main.output` nếu muốn main artifact |
| Nhiều entry trùng path | Nhiều sources cùng relative path | Đặt `DuplicatesStrategy.FAIL`, sửa CopySpec |
| Script Unix báo permission denied | Executable bit bị mất khi archive/copy/extract | Thiết lập archive permissions, smoke test trên OS |
| TAR extract sai permissions | Tool/format/copy rules khác | Kiểm tar headers, filePermissions và target OS |
| ZIP/TAR thay SHA-256 giữa hai builds | Timestamp/order/permissions/inputs khác | Pin toolchain/deps; reproducibility flags và so entry metadata |
| Archive có file secret ngoài ý muốn | CopySpec dùng `from(".")` quá rộng | Chỉ liệt kê nội dung cần ship, exclude secrets, scan archive |
| `Could not find commons-lang3` | Repo/network/dependency coordinates không đúng | Kiểm `mavenCentral()`, dependency graph, credentials |
| `build` fail vì unit test dù JAR đã tạo | `build` gồm `check`/`test` | Sửa test, dùng `jar` khi chỉ cần debug artifact |
| `sourcesJar` được tạo nhưng không chạy | Nó chứa source, không có compiled class | Sử dụng binary JAR trong runtime |
| Downstream consumer thiếu dependency khi copy JAR | File JAR không mang module graph đầy đủ | Publish Maven/Ivy metadata, không chỉ đưa file |
| `java -jar` với `-cp` vẫn thiếu dependency | `-jar` không kết hợp classpath như dự đoán | Dùng generated start scripts hoặc `java -cp ... demo.Main` |
| Application installer không chạy nếu máy chưa có Java | Default distribution không bundle JVM | Cài runtime, hoặc dùng jlink/jpackage/image chuyên dụng |

## 17. Một quy trình kiểm chứng task graph có ích

Các lệnh thực hành:

```bash
./gradlew tasks --all
./gradlew classes --dry-run
./gradlew jar --dry-run
./gradlew distZip --dry-run
./gradlew assemble --dry-run
./gradlew check --dry-run
```

**`--dry-run` chỉ lập kế hoạch, không thực thi tasks.** Dùng nó để biết:

- `classes` thường yêu cầu `compileJava` và `processResources`.
- `jar` cần main outputs, nên compile/resource tasks được Gradle nối.
- `distZip` cần `jar`, `startScripts` và runtime artifacts.
- `assemble` có thể yêu cầu `distZip`/`distTar` do Distribution plugin.
- `check` chủ yếu là verification tasks, không tự phải tạo mọi distribution outputs.

Sau khi đọc graph, chạy task thật mới kiểm tra file content:

```bash
./gradlew clean classes
./gradlew jar
./gradlew distZip
./gradlew installDist
```

Không lấy việc một file cũ tồn tại làm bằng chứng task vừa chạy; xem console outcome hoặc dùng `clean` trong sandbox có kiểm soát.

## 18. Windows, Linux và macOS: lệnh tương đương

| Công việc | Linux/macOS | Windows PowerShell |
| --- | --- | --- |
| Gọi Gradle Wrapper | `./gradlew jar` | `.\gradlew.bat jar` |
| Chạy installed app | `./build/install/archive-lab/bin/archive-lab` | `.\build\install\archive-lab\bin\archive-lab.bat` |
| Xem JAR | `jar tf build/libs/archive-lab-1.0.0.jar` | `jar tf build\libs\archive-lab-1.0.0.jar` |
| Xem ZIP | `unzip -l path.zip` | `Expand-Archive` vào directory tạm rồi `Get-ChildItem` |
| Xem TAR | `tar -tf path.tar` | `tar -tf path.tar` (nếu có tar) |
| Xem TAR.GZ | `tar -tzf path.tar.gz` | `tar -tzf path.tar.gz` (nếu có tar) |
| SHA-256 | `sha256sum path.zip` | `Get-FileHash path.zip -Algorithm SHA256` |

**Lưu ý:** macOS thường có `shasum -a 256` thay vì `sha256sum`. Các lệnh trên phụ thuộc công cụ thực có trong shell; `jar` có sẵn khi JDK được cài, `tar`/`unzip` có thể cần bổ sung trong môi trường tối giản.

### 18.1. Giải nén ZIP để chạy trên một directory mới

Linux/macOS:

```bash
mkdir -p build/unpacked
unzip build/distributions/archive-lab-1.0.0.zip -d build/unpacked
./build/unpacked/archive-lab-1.0.0/bin/archive-lab
```

Nếu ZIP extraction tool không giữ executable bit, script có thể báo permission denied; khắc phục permissions theo policy hoặc dùng `sh ./build/unpacked/archive-lab-1.0.0/bin/archive-lab` cho smoke test. **Không thay permission bừa trên files lạ**.

Windows PowerShell:

```powershell
Expand-Archive build\distributions\archive-lab-1.0.0.zip -DestinationPath build\unpacked
.\build\unpacked\archive-lab-1.0.0\bin\archive-lab.bat
```

Các lệnh này chỉ chạy đúng khi ZIP đã được tạo trước đó bằng `distZip`. Với `artifactZip` custom, không có script `bin/archive-lab` nên không dùng chung lệnh.

### 18.2. Chạy TAR distribution

Linux/macOS:

```bash
mkdir -p build/unpacked-tar
tar -xf build/distributions/archive-lab-1.0.0.tar -C build/unpacked-tar
./build/unpacked-tar/archive-lab-1.0.0/bin/archive-lab
```

TAR format bảo lưu nhiều POSIX metadata hơn ZIP, nhưng vẫn cần kiểm tra executability, owner/group và symlinks theo OS/file system đích. Dùng sandbox directory để giải nén trong CI, không giải nén trực tiếp vào system directories.

## 19. Khi build nhiều module: chọn artifact đúng scope

Giả sử:

```text
root/
├── settings.gradle.kts
├── core/build.gradle.kts
├── server/build.gradle.kts
└── cli/build.gradle.kts
```

Nếu `:core` dùng `java-library`, còn `:server`/`:cli` dùng `application`:

- `:core:jar` tạo library JAR; nó không tự tạo server ZIP.
- `:server:distZip` tạo phân phối cho server, gồm runtime dependencies (có thể gồm `core` artifact).
- `:cli:distTar` tạo phân phối cho CLI khác, có entry point và start scripts riêng.
- `:server:assemble` có thể tạo cả jar/distributions của `server`.
- Root `assemble` không nên được dùng để suy đoán output từng module nếu task wiring khác; dùng fully-qualified task path.
- `project(":core")` dependency giúp Gradle nối tasks/variants thay vì yêu cầu người ta copy `core/build/libs/core.jar` bằng tay.

Ví dụ consumer:

```kotlin
// server/build.gradle.kts
dependencies {
    implementation(project(":core"))
}
```

Đây là **đoạn minh họa**, chưa phải build script độc lập nếu thiếu plugins/settings. Với Application plugin trong `:server`, runtime classpath sẽ bao gồm artifact/dependencies phù hợp của `:core` theo Java variants.

Khi cần một release bao gồm **nhiều ứng dụng**, tạo một distribution có layout rõ thay vì zip toàn bộ root `build/`. Không làm release package bằng `from(".")` không lọc, vì có thể mang cả keys, logs, caches, build reports hoặc local config chứa secrets.

## 20. Câu hỏi tự kiểm tra

1. **`classes` và `jar` khác nhau điều gì?** `classes` tạo outputs của compile/resources, `jar` đóng gói main outputs thành Java archive.
2. **JAR có phải ZIP không?** JAR có cấu trúc ZIP-compatible, nhưng còn quy tắc Java/manifest; không phải mọi ZIP đều là Java module hợp lệ.
3. **`java -jar` có tự resolve Maven dependencies không?** Không. JVM không hỏi Maven Central/Gradle để tải `implementation(...)`.
4. **Có `Main-Class` là đủ để JAR có dependency Commons Lang chạy chưa?** Chưa. Cần dependency trên runtime classpath hoặc packaging đầy đủ.
5. **`run` dùng lớp nào của Gradle Application plugin?** JavaExec task sử dụng main output và runtime classpath.
6. **`distZip`/`distTar` khác custom `Zip`/`Tar` ở đâu?** Application distribution có layout/launch scripts/runtime libs theo plugin, còn custom archive chỉ gồm nội dung CopySpec khai báo.
7. **Tại sao `distTar` mặc định không phải `tar.gz`?** TAR không tự nén; phải cấu hình GZIP và extension hoặc custom Tar.
8. **`installDist` có tạo ZIP không?** Không. Nó tạo directory tree đã assemble; `distZip` tạo file ZIP.
9. **`assemble` của Application project có tạo TAR/ZIP không?** Thông thường có, vì Distribution plugin wire các archive tasks vào `assemble`.
10. **`check` và `build` khác nhau?** `check` chạy verification; `build` tổng hợp assemble và check.
11. **Custom `artifactZip` có tự chạy khi `assemble` chạy không?** Không, trừ khi được nối vào lifecycle dependency.
12. **Vì sao dùng `from(tasks.named("jar"))` tốt hơn `from("build/libs/foo.jar")`?** TaskProvider mô tả producer output và dependency, không hardcode tên/đường file dễ đổi.
13. **Bật reproducible file order đã đủ để ZIP/JAR cùng SHA-256 giữa hai máy?** Chưa, phải kiểm dependency/toolchain/inputs/generated contents.
14. **TAR có luôn giữ quyền execute trên máy đích không?** Metadata có thể được lưu nhưng extraction/OS có thể thay đổi; cần smoke test.
15. **Source JAR có thể dùng chạy ứng dụng không?** Không, nó chứa source chứ không phải compiled classes.
16. **`maven-publish` và `distZip` có cùng trách nhiệm không?** Không; publishing tạo module artifact/metadata cho repository, distZip tạo archive giao cho người dùng/ops.
17. **Fat JAR có phải output mặc định của `jar` không?** Không. Cần packaging logic/tool chuyên dụng và xử lý duplicate/licensing.
18. **Ứng dụng đóng ZIP có cần JDK/JRE trên máy đích không?** Default Application distribution cần Java runtime tương thích; nó không tự mang JRE.

## 21. Checklist trước khi giao bản build

- [ ] Xác định consumer: JVM developer, end user, CI, server ops hay Maven repository.
- [ ] Dùng `classes` cho compiled outputs, `jar` cho Java artifact, `distZip`/`distTar` cho application distribution.
- [ ] Java source/resource paths và `sourceSets.main.output` được Gradle quản lý đúng.
- [ ] JAR chứa class/resources cần thiết; test classes chỉ được thêm khi có chủ đích.
- [ ] Nếu sử dụng `java -jar`, manifest Main-Class và runtime classpath/bundling thực sự phù hợp.
- [ ] Nếu dùng Application distribution, scripts `bin/` và JARs `lib/` chạy trên máy mới.
- [ ] ZIP/TAR có file config/docs/license đúng vị trí, không lộ secrets/keys/logs.
- [ ] Custom archive `from(...)` dùng TaskProvider/Provider cho generated outputs.
- [ ] Không tạo duplicate entries hoặc dùng policy duplicate mập mờ.
- [ ] TAR.GZ có cả `Compression.GZIP` và extension đúng.
- [ ] Archive filenames/version/classifier rõ, destination paths không đè lẫn nhau.
- [ ] Kiểm quyền thực thi Unix scripts và behavior trên Windows khi cần.
- [ ] Có reproducible archive settings phù hợp Gradle version, pin toolchain/deps.
- [ ] Đã chạy `jar tf`/`unzip -l`/`tar -tf` để kiểm layout thay vì nhìn filename.
- [ ] Đã test runtime **từ distribution giải nén/installed**, không chỉ `./gradlew run`.
- [ ] Nếu publish library, metadata POM/Gradle Module Metadata đầy đủ, không chỉ file JAR.
- [ ] Có SHA-256/provenance/license policy cho release binaries.
- [ ] CI chạy đúng task và archive reports/checksums trước khi deploy.

## 22. Ghi nhớ

- **`classes` = compile + resources**, không phải archive.
- **`jar` = Java archive** chứa main source-set outputs, không mặc định bao gồm tất cả runtime dependency JARs.
- **`Zip` và `Tar` là task types xây archives bằng CopySpec**; bản thân format không chứng minh nội dung có thể chạy.
- **`application` tự áp dụng Java + Distribution**, cung cấp `run`, `startScripts`, `installDist`, `distZip`, `distTar`.
- **Application distribution** chứa launch scripts và runtime libraries, khác một custom ZIP/TAR chỉ chứa app JAR.
- **`distTar` thường ra TAR không nén**; muốn TAR.GZ cần bật GZIP.
- **`assemble` có thể kéo các dist archives**, `build` kéo assemble + check, `check` không cần đóng gói.
- **Archive naming là các properties riêng**: baseName/version/classifier/extension/destinationDirectory.
- **Gradle 9+ mặc định reproducible archive order/timestamps/permissions**, nhưng build reproducibility vẫn cần inputs và toolchains ổn định.
- **Publishing** một library/module là việc khác với tạo file ZIP/TAR để giao cho người chạy.

## Tài liệu chính thức

- [Gradle — The Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): `compileJava`, `processResources`, `classes`, `jar`, source sets và task lifecycle.
- [Gradle — The Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): `run`, `startScripts`, `installDist`, `distZip`/`distTar`, application distribution layout và runtime dependencies.
- [Gradle — The Distribution Plugin](https://docs.gradle.org/current/userguide/distribution_plugin.html): `distZip`, `distTar`, `assembleDist`, `installDist`, `src/dist`, `assemble` wiring.
- [Gradle — Working with Files / Creating Archives](https://docs.gradle.org/current/userguide/working_with_files.html): `Jar`, `Zip`, `Tar`, `CopySpec`, archive names, duplicate files, reproducibility, compression.
- [Gradle — AbstractArchiveTask API](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.AbstractArchiveTask.html): archive properties, `reproducibleFileOrder` và `preserveFileTimestamps`.
- [Gradle — Tar Task API](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.Tar.html): `Compression.GZIP` và TAR archive settings.
- [Gradle — Jar Task API](https://docs.gradle.org/current/dsl/org.gradle.jvm.tasks.Jar.html): `Jar` task/manifest behavior và ZIP format.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): Java library components, API/runtime variants và source/Javadoc outputs.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): xuất bản Maven module artifact, POM/Gradle Module Metadata.
- [Gradle — Best Practices for Security](https://docs.gradle.org/current/userguide/best_practices_security.html): Gradle Wrapper, reproducible archives và security policies.

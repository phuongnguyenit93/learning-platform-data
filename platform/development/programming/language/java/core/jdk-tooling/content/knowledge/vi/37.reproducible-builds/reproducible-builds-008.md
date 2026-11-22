# Môi trường build trong Java

**Môi trường build** là tập hợp công cụ, runtime, hệ điều hành, cấu hình, biến môi trường, dependency và dữ liệu bên ngoài tham gia tạo ra artifact. Với cùng một commit, hai lần build chỉ có thể cho kết quả giống nhau khi các đầu vào ảnh hưởng đến artifact được xác định và kiểm soát.

Một build có thể chạy thành công trên máy developer nhưng tạo JAR khác với CI vì khác JDK patch, Gradle/Maven version, locale, timezone, file permission, dependency được tải, thời gian hệ thống hoặc biến môi trường. Những khác biệt này làm giảm khả năng tái hiện lỗi và gây khó khăn khi xác minh artifact đã phát hành.

Mục tiêu là thiết lập môi trường build Java có thể mô tả, kiểm tra và tái tạo. Cần phân biệt hai khái niệm:

- **Reproducible build:** cùng source và cùng các đầu vào được kiểm soát tạo ra artifact giống nhau theo byte.
- **Hermetic build:** build chỉ sử dụng các đầu vào đã khai báo, không phụ thuộc ngầm vào trạng thái máy, mạng hoặc tài nguyên bên ngoài chưa được kiểm soát.

Một build hermetic có thể chưa reproducible nếu timestamp, thứ tự file hoặc random seed thay đổi. Ngược lại, hai build tình cờ cho cùng output không chứng minh toàn bộ môi trường đã được kiểm soát.

## 1. Những thành phần tạo nên môi trường build

Với dự án Java, cần xem xét ít nhất các lớp sau:

| Thành phần | Ví dụ đầu vào | Cách kiểm soát |
|---|---|---|
| JDK | Vendor, major/patch version, architecture | Java toolchain, image hoặc package đã pin |
| Build tool | Gradle/Maven và wrapper distribution | Gradle Wrapper hoặc Maven Wrapper |
| Plugin và dependency | Gradle plugin, Maven plugin, thư viện | Version cố định, dependency lock và checksum |
| Hệ điều hành | Linux distribution, Windows, macOS | Runner image/container cố định |
| Kiến trúc | x86_64, ARM64 | Chọn platform rõ ràng |
| Locale/encoding | Ngôn ngữ, charset, collation | LANG, LC_ALL, UTF-8 và Locale rõ ràng |
| Timezone/clock | UTC, thời gian hiện tại | TZ=UTC, timestamp xác định |
| Filesystem | Path, case sensitivity, permissions | Workspace sạch, layout nhất quán |
| Environment variables | JAVA_HOME, PATH, proxy, flags | Whitelist và cấu hình versioned |
| Network/repository | Maven Central, plugin portal, mirror | Repository ổn định, dependency verification |
| Generated output | Code generation, archive timestamps | Task inputs/outputs khai báo rõ |
| CI runner | Agent, image, action/plugin | Version pinning và log môi trường |

Không phải mọi khác biệt đều ảnh hưởng đến mọi artifact. Ví dụ, locale có thể không ảnh hưởng đến JAR chỉ chứa class thuần Java, nhưng có thể làm thay đổi resource được sinh từ template hoặc dữ liệu được sort theo collation. Cần xác định đầu vào nào thực sự tham gia vào build của dự án.

## 2. Phân biệt môi trường build với source code và build configuration

Source code mô tả chương trình. Build configuration mô tả cách biên dịch và đóng gói. Môi trường build cung cấp runtime và hệ thống mà các cấu hình đó thực thi.

Ví dụ, file build.gradle.kts có thể yêu cầu Java toolchain 17, nhưng CI vẫn có thể chạy Gradle bằng JDK 25. Cả hai version đều là một phần của môi trường và phải được ghi nhận.

Một dự án có thể khai báo:

- JDK dùng để chạy Gradle.
- JDK compiler dùng để compile.
- Java release target mà artifact hỗ trợ.
- Gradle Wrapper distribution.
- Dependency và plugin version.
- Container image chạy build.
- Locale, timezone và các biến môi trường quan trọng.

Một cấu hình build tốt khai báo các yêu cầu cần thiết thay vì giả định máy chạy đã được cài đúng công cụ.

## 3. Cố định JDK và Java toolchain

JDK có thể khác nhau theo vendor, version, patch level và kiến trúc. Hai bản cùng major version vẫn có thể khác compiler, implementation, security provider hoặc bug fix.

Gradle Java Toolchains giúp chọn JDK cho compile/test task:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
        vendor.set(JvmVendorSpec.ADOPTIUM)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}
```

Cấu hình trên yêu cầu JDK 17 thuộc vendor Adoptium cho các task dùng toolchain, đồng thời giới hạn ngôn ngữ/API/bytecode theo Java 17 và dùng UTF-8 khi compile.

Toolchain theo major version chưa cố định patch version. Nếu yêu cầu build nghiêm ngặt cần xác định chính xác JDK build, hãy dùng một JDK distribution đã pin trong container image hoặc package archive có checksum đã xác minh. Ghi lại output của java --version, javac --version, vendor và architecture trong build metadata.

Cũng cần phân biệt JVM chạy Gradle với JDK toolchain của compiler. Kiểm tra bằng:

```sh
java --version
javac --version
./gradlew --version
./gradlew -q javaToolchains
```

Nếu java --version hiển thị JDK khác với compiler toolchain, điều đó có thể đúng theo thiết kế. Hãy ghi nhận cả hai giá trị.

## 4. Cố định Gradle hoặc Maven bằng Wrapper

Không phụ thuộc vào Gradle/Maven được cài global trên runner. Commit wrapper vào repository để developer và CI gọi cùng build tool distribution.

Gradle Wrapper dùng file gradle/wrapper/gradle-wrapper.properties:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.0-bin.zip
```

Khi cần bảo vệ tính toàn vẹn của distribution, thêm thuộc tính distributionSha256Sum với checksum thật lấy từ trang phân phối chính thức của đúng file ZIP đã chọn. Không sao chép checksum của version hoặc archive khác.

Các file wrapper cần được quản lý trong Git:

- gradlew
- gradlew.bat
- gradle/wrapper/gradle-wrapper.jar
- gradle/wrapper/gradle-wrapper.properties

Chạy ./gradlew --version để xác nhận distribution thực tế. Khi nâng Gradle, thay đổi wrapper trong pull request riêng, kiểm tra release notes, plugin compatibility và toàn bộ build.

Với Maven, dùng Maven Wrapper (mvnw, mvnw.cmd và .mvn/wrapper). Pin Maven distribution trong maven-wrapper.properties, xác minh checksum nếu wrapper version hỗ trợ và chạy ./mvnw --version trong CI.

Wrapper cố định build tool, nhưng không tự cố định JDK, plugin, dependency, OS hay container image. Các lớp đó cần được kiểm soát riêng.

## 5. Cố định hệ điều hành và container image

Một build chạy trên Ubuntu, Windows và macOS có thể gặp khác biệt về path separator, filesystem case sensitivity, shell, permission, native library và tool được cài sẵn.

Nếu build trong container, image là một đầu vào quan trọng. Tag như eclipse-temurin:17-jdk giúp chọn dòng JDK, nhưng tag có thể được cập nhật. Với build cần tính bất biến cao, pin image bằng digest lấy trực tiếp từ registry tin cậy. Digest phải ứng với đúng image/platform; không tự tạo hoặc sao chép digest từ image khác.

Ví dụ Dockerfile multi-stage:

```dockerfile
FROM eclipse-temurin:17-jdk AS build
WORKDIR /workspace

COPY gradlew .
COPY gradle gradle
COPY settings.gradle.kts build.gradle.kts ./
RUN chmod +x gradlew

COPY src src
RUN ./gradlew --no-daemon clean build

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /workspace/build/libs/*.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
```

Đây là ví dụ về cấu trúc multi-stage. Để đạt mức pin bất biến, thay cả hai FROM bằng image reference có digest đã xác minh. Image build stage và runtime stage là hai đầu vào riêng.

Một container không đóng băng toàn bộ host. Kernel, CPU architecture, container runtime và cấu hình build platform vẫn có thể khác nhau. Nếu tạo native binary, JNI library hoặc artifact phụ thuộc CPU, phải cố định thêm target architecture và toolchain native.

## 6. Chọn architecture và platform rõ ràng

Không mặc định x86_64 và ARM64 tạo cùng artifact. Bytecode Java thuần thường portable, nhưng native image, JNI library, compressed asset, generated binary hoặc dependency có native classifier có thể khác theo architecture.

Trong CI:

- Ghi rõ runner architecture.
- Chọn Docker platform khi build image đa kiến trúc.
- Không trộn cache output native giữa x86_64 và ARM64.
- Tách job matrix theo OS/architecture nếu sản phẩm hỗ trợ nhiều nền tảng.
- Xác minh artifact được tạo đúng target platform trước khi publish.

Nếu chỉ cần JAR thuần Java, có thể build một lần trên platform chuẩn và chạy test compatibility trên các runtime khác. Nếu đóng gói native library, cần build và kiểm thử riêng cho từng platform được hỗ trợ.

## 7. Chuẩn hóa locale, charset và timezone

Locale mặc định ảnh hưởng đến cách format số/ngày, sort chuỗi, xử lý chữ hoa/thường và một số thư viện. Charset mặc định ảnh hưởng đến việc đọc/ghi text nếu code không chỉ định encoding.

Ví dụ, format số theo locale có thể cho kết quả khác:

- Locale dùng dấu phẩy thập phân: 12,50.
- Locale dùng dấu chấm thập phân: 12.50.

Đối với dữ liệu hoặc output cần ổn định, chỉ định locale rõ ràng trong code:

```java
import java.util.Locale;

public class FormatDemo {
    public static void main(String[] args) {
        String value = String.format(Locale.ROOT, "%.2f", 12.5);
        System.out.println(value);
    }
}
```

Biên dịch và chạy:

```sh
javac FormatDemo.java
java FormatDemo
```

Stdout:

```text
12.50
```

Locale.ROOT phù hợp cho format machine-readable không phụ thuộc ngôn ngữ người dùng. Với nội dung hiển thị cho người dùng, chọn locale nghiệp vụ rõ ràng thay vì luôn ép ROOT.

Trong CI, có thể chuẩn hóa:

```sh
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export TZ=UTC
```

Đồng thời đặt encoding trong compiler/build tool:

- Gradle JavaCompile: options.encoding = "UTF-8".
- Maven: project.build.sourceEncoding=UTF-8.
- Khi đọc/ghi file trong Java, truyền StandardCharsets.UTF_8 rõ ràng.

Không dùng locale hệ thống làm quy tắc sort hoặc format dữ liệu nghiệp vụ nếu kết quả phải reproducible. Hãy chọn Locale.ROOT, locale cụ thể hoặc comparator xác định trong code.

## 8. Kiểm soát timezone và thời gian hệ thống

Thời gian hiện tại là một đầu vào ẩn phổ biến. Build có thể tạo artifact khác nhau nếu ghi ngày build, timestamp, thời điểm sinh source hoặc thời gian trong manifest.

Đặt timezone của job thành UTC giúp log và công cụ xử lý thời gian nhất quán:

```sh
export TZ=UTC
date -u
```

Tuy nhiên, timezone UTC không làm đồng hồ trở thành cố định. Nếu code gọi Instant.now() hoặc System.currentTimeMillis() để ghi vào artifact, mỗi lần build vẫn có thể khác.

Các nguyên tắc:

- Không nhúng wall-clock time vào artifact nếu không cần.
- Nếu cần timestamp build, dùng giá trị ổn định gắn với source revision hoặc release, không lấy thời gian hiện tại tùy ý.
- Truyền timestamp cố định vào code generator hoặc archive task có hỗ trợ.
- Không dùng LocalDateTime.now() làm dữ liệu build mặc định.
- Dùng UTC và Instant cho thời điểm thực tế; dùng Clock được inject khi cần kiểm thử.

SOURCE_DATE_EPOCH là quy ước được nhiều công cụ build/release hỗ trợ để cung cấp timestamp ổn định. Không phải mọi Java plugin hay task tự động đọc biến này; cần kiểm tra tài liệu công cụ và truyền giá trị vào đúng task hoặc archive configuration.

## 9. Kiểm soát biến môi trường

Biến môi trường có thể thay đổi JVM, build tool, dependency resolution và code generator. Một số biến thường cần xem xét:

| Biến | Ảnh hưởng |
|---|---|
| JAVA_HOME | JVM mặc định dùng để chạy Gradle/Maven |
| PATH | Phiên bản java, javac, shell và công cụ được gọi |
| JAVA_TOOL_OPTIONS | JVM options được inject vào process Java |
| _JAVA_OPTIONS | JVM options bổ sung trên một số runtime |
| GRADLE_OPTS | JVM options cho Gradle client |
| MAVEN_OPTS | JVM options cho Maven |
| GRADLE_USER_HOME | Gradle cache, init script và cấu hình user |
| HOME / USERPROFILE | Maven/Gradle config và file user-level |
| TMPDIR / TEMP | Thư mục temporary |
| LANG / LC_ALL | Locale và charset |
| TZ | Timezone |
| HTTP_PROXY / HTTPS_PROXY | Đường đi truy cập repository |
| CI / BUILD_NUMBER | Build script hoặc plugin có thể dùng làm metadata |

Không dump toàn bộ environment vào log vì có thể làm lộ token, password, signing key hoặc credential repository. Chỉ ghi whitelist các biến không nhạy cảm và ghi nhận tên secret được cấu hình mà không in giá trị.

Build script không nên âm thầm thay đổi kết quả theo BUILD_NUMBER, tên branch, username hoặc đường dẫn home. Nếu cần metadata này, quyết định rõ nó có phải một phần của artifact hay chỉ là log ngoài artifact.

## 10. Cố định filesystem, path và file permissions

Filesystem khác nhau có thể làm thay đổi kết quả build:

- Linux thường phân biệt chữ hoa/thường trong tên file; một số filesystem Windows/macOS mặc định không phân biệt.
- Path separator khác nhau (/ và \).
- Permission bit và executable bit khác nhau.
- Symbolic link có thể được xử lý khác tùy OS và runner.
- Thứ tự liệt kê file từ filesystem không nên được coi là thứ tự ổn định.
- Line ending có thể là LF hoặc CRLF.

Để giảm khác biệt:

1. Dùng workspace sạch cho mỗi lần build.
2. Không phụ thuộc vào file còn sót từ lần build trước.
3. Sort danh sách file trước khi đưa vào generator hoặc archive.
4. Dùng path API của Java (Path, Paths) thay vì nối chuỗi path thủ công.
5. Chuẩn hóa line ending bằng .gitattributes.
6. Kiểm soát executable bit của script trong Git.
7. Không dùng absolute path của workspace làm nội dung artifact.

Ví dụ .gitattributes:

```gitattributes
*.java text eol=lf
*.kt text eol=lf
*.kts text eol=lf
*.properties text eol=lf
*.sh text eol=lf
*.bat text eol=crlf
```

Cấu hình này giúp Git checkout các loại file theo line ending đã chọn. Khi thêm file mới, kiểm tra git diff --check và trạng thái line ending trước khi build.

## 11. Dependency repositories và network

Build có thể không reproducible nếu dependency được resolve từ version động hoặc repository thay đổi nội dung theo thời gian.

Tránh khai báo:

- Dynamic version như 1.+.
- Version range không được khóa.
- Snapshot dependency thay đổi cùng coordinate.
- Plugin version không cố định.
- Repository nội bộ ghi đè artifact cùng tọa độ.
- Download trực tiếp một file không có checksum xác minh.

Nên:

- Ghi rõ version dependency và plugin.
- Dùng dependency locking để lưu graph đã resolve.
- Bật dependency verification bằng checksum/signature.
- Dùng repository tin cậy và quy định thứ tự/nguồn artifact.
- Không publish lại artifact khác nội dung dưới cùng group/name/version.
- Lưu artifact đã phát hành trong repository immutable.
- Ghi nhận mirror/proxy nếu nó là một phần của đường dependency resolution.

Với Gradle, có thể bật dependency locking:

```kotlin
dependencyLocking {
    lockAllConfigurations()
}
```

Sau khi cấu hình, resolve các configuration cần thiết và ghi lock state:

```sh
./gradlew build --write-locks
```

Dependency verification có thể tạo metadata SHA-256:

```sh
./gradlew --write-verification-metadata sha256 help
```

Kiểm tra và review file lock/verification metadata trước khi commit. Không tự động chấp nhận checksum mới mà không xác minh nguồn dependency.

## 12. Quản lý plugin và build logic

Plugin cũng là dependency của build. Một plugin mới có thể thay đổi task graph, compiler arguments, archive metadata hoặc cách resolve dependency.

Các thực hành tốt:

- Pin version plugin trong plugins block hoặc plugin management.
- Không dùng dynamic version cho plugin production.
- Kiểm tra plugin compatibility với Gradle/Maven và JDK.
- Version hóa convention plugin và build logic trong repository.
- Review init script và global Gradle/Maven settings vì chúng có thể thay đổi build mà không xuất hiện trong repository.
- Hạn chế phụ thuộc vào plugin được cài riêng trên runner.

GRADLE_USER_HOME có thể chứa init.gradle, init.d và cache ảnh hưởng đến build. Với CI reproducible, dùng user home riêng hoặc kiểm soát nội dung init script; không dựa vào cấu hình global không được version hóa.

## 13. Chuẩn hóa Gradle build environment

Ví dụ gradle.properties:

```properties
org.gradle.jvmargs=-Dfile.encoding=UTF-8 -Duser.timezone=UTC
org.gradle.caching=true
org.gradle.daemon=false
```

Các thuộc tính trên chuẩn hóa encoding/timezone cho Gradle JVM, bật build cache và tắt daemon trong môi trường CI để giảm ảnh hưởng của process còn sống giữa các job. Tùy kiến trúc runner, có thể dùng daemon để tăng tốc; điều quan trọng là không để state cũ làm thay đổi output.

Cấu hình archive task để thứ tự file và timestamp ổn định:

```kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
```

isPreserveFileTimestamps = false chuẩn hóa timestamp entry trong archive; isReproducibleFileOrder = true yêu cầu thứ tự entry ổn định. Các thiết lập này không tự sửa timestamp hoặc nội dung được code generator ghi vào file trước khi archive.

Có thể tạo task ghi lại một số thuộc tính môi trường không nhạy cảm:

```kotlin
tasks.register("printBuildEnvironment") {
    doLast {
        println("gradle=" + gradle.gradleVersion)
        println("java.version=" + System.getProperty("java.version"))
        println("java.vendor=" + System.getProperty("java.vendor"))
        println("os.name=" + System.getProperty("os.name"))
        println("os.arch=" + System.getProperty("os.arch"))
        println("user.timezone=" + System.getProperty("user.timezone"))
        println("file.encoding=" + System.getProperty("file.encoding"))
    }
}
```

Chạy:

```sh
./gradlew printBuildEnvironment
```

Task này chỉ ghi thông tin chẩn đoán; không nên đưa thông tin máy như username hoặc absolute workspace path vào artifact.

## 14. Chuẩn hóa Maven build environment

Với Maven, khai báo encoding, Java release và output timestamp:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
    <project.build.outputTimestamp>2025-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
```

Timestamp trong ví dụ là giá trị cố định minh họa. Trong dự án thật, có thể truyền timestamp xác định từ source revision hoặc release process, miễn là mọi build so sánh đều nhận cùng giá trị.

Một số Maven plugin và archive component cần version được pin rõ ràng. Ví dụ:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
            <configuration>
                <release>17</release>
                <encoding>UTF-8</encoding>
            </configuration>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
        </plugin>
    </plugins>
</build>
```

Các version trên là ví dụ minh họa cho cách pin plugin; kiểm tra compatibility và chọn version đã được tổ chức phê duyệt trước khi sử dụng. Dùng Maven Wrapper để cố định Maven distribution và Maven Enforcer Plugin nếu cần kiểm tra version Maven/JDK tối thiểu.

## 15. Generated sources và code generation

Generated source thường là nguồn gây khác biệt vì tool có thể nhúng timestamp, absolute path, thứ tự input hoặc version generator vào output.

Ví dụ các công cụ sinh mã:

- OpenAPI Generator.
- Protocol Buffers compiler.
- JAXB/XJC.
- Annotation processor.
- SQL/schema code generator.
- Frontend asset bundler được gọi từ Gradle/Maven.

Để kết quả ổn định:

1. Pin version generator và plugin.
2. Khai báo schema/input file đầy đủ.
3. Sort danh sách input nếu thứ tự có ý nghĩa.
4. Không nhúng thời gian hiện tại vào generated file.
5. Không nhúng absolute path hoặc username.
6. Cố định locale/encoding.
7. Khai báo task dependency để generator chạy trước compile.
8. Ghi output vào thư mục build riêng, không sửa source do developer quản lý.
9. Kiểm tra generated file có khác giữa hai build hay không.

Task generator phải khai báo input/output để Gradle biết khi nào task cần chạy lại và có thể cache output. Một task phụ thuộc vào biến môi trường hoặc file ngoài repository mà không khai báo input có thể trả lại output cache không còn đúng.

## 16. Randomness, parallelism và thứ tự xử lý

Build script hoặc generator có thể tạo output không ổn định nếu dùng random number, concurrent collection không có thứ tự hoặc thứ tự duyệt file không xác định.

Ví dụ, không dựa vào thứ tự iteration của HashSet để tạo file config. Hãy sort trước khi serialize:

```java
import java.util.List;

public class StableOrderDemo {
    public static void main(String[] args) {
        List<String> names = List.of("gamma", "alpha", "beta");
        String output = names.stream()
                .sorted()
                .reduce((left, right) -> left + "," + right)
                .orElse("");

        System.out.println(output);
    }
}
```

Biên dịch và chạy:

```sh
javac StableOrderDemo.java
java StableOrderDemo
```

Stdout:

```text
alpha,beta,gamma
```

Nếu cần random trong build/test, dùng seed được khai báo rõ ràng và ghi seed vào log. Không dùng System.nanoTime() hoặc thời gian hiện tại làm seed khi cần kết quả lặp lại.

Parallel build có thể thay đổi thứ tự log hoặc bộc lộ task thiếu khai báo dependency. Task output không được phụ thuộc vào thứ tự thực thi ngẫu nhiên. Khai báo task inputs/outputs và dependency graph đầy đủ; chỉ tắt parallelism để khoanh vùng race, không coi đó là cách sửa lỗi lâu dài.

## 17. Cách ghi nhận build environment mà không lộ secret

Mỗi CI build nên lưu một manifest môi trường bên ngoài artifact hoặc như build metadata có chủ đích.

Có thể ghi:

- Git commit SHA và trạng thái working tree.
- JDK vendor/version/architecture.
- Gradle/Maven Wrapper version.
- OS/container image và digest.
- Locale, timezone và encoding.
- Runner OS/architecture.
- Plugin/dependency lock state.
- Các biến môi trường không nhạy cảm có ảnh hưởng build.
- Thời điểm hoặc source timestamp nếu build cần dùng timestamp.
- Command line đã chạy.

Ví dụ lệnh ghi nhận trong Linux CI:

```sh
git rev-parse HEAD
git status --short
java --version
javac --version
./gradlew --version
uname -a
locale
date -u
printenv LANG LC_ALL TZ JAVA_HOME
```

Lệnh trên chỉ in các biến được chọn. Không dùng env, printenv không tham số hoặc set trong log CI nếu environment có secret.

Trên Windows PowerShell, có thể ghi:

```powershell
git rev-parse HEAD
java --version
javac --version
.\gradlew.bat --version
Get-Culture
Get-TimeZone
$env:JAVA_HOME
$env:PROCESSOR_ARCHITECTURE
```

Lưu manifest cùng log build hoặc artifact provenance. Tránh nhúng đường dẫn cá nhân, token, hostname nhạy cảm hoặc thông tin bí mật vào public artifact.

## 18. Kiểm chứng bằng hai lần build sạch

Một cách kiểm tra thực tế là build cùng commit trong hai workspace độc lập, không dùng output từ lần trước.

Quy trình:

1. Checkout cùng commit SHA vào hai thư mục khác nhau.
2. Dùng cùng JDK, Wrapper, container image, dependency lock và cấu hình môi trường.
3. Dùng cache riêng hoặc build offline sau khi đã tải dependency đúng phiên bản.
4. Chạy cùng command, ví dụ ./gradlew --no-daemon clean build.
5. Lấy artifact từ mỗi workspace.
6. So sánh checksum SHA-256.
7. Nếu checksum khác, kiểm tra nội dung archive, timestamp, thứ tự entry và generated file.

Ví dụ Linux:

```sh
sha256sum build-a/build/libs/app.jar
sha256sum build-b/build/libs/app.jar
```

Nếu hai checksum giống nhau, hai file có cùng bytes. Nếu khác nhau, kiểm tra chi tiết:

```sh
unzip -l build-a/build/libs/app.jar
unzip -l build-b/build/libs/app.jar
diffoscope build-a/build/libs/app.jar build-b/build/libs/app.jar
```

diffoscope giúp chỉ ra khác biệt sâu bên trong archive nếu công cụ đã được cài đặt. Có thể dùng jar tf để so sánh danh sách entry và giải nén hai JAR để so sánh từng file.

Không so sánh hai build trên JDK/OS khác nhau rồi kết luận build không reproducible nếu mục tiêu kiểm thử là cùng môi trường. Trước tiên phải so sánh hai môi trường tương đương; sau đó mới mở rộng sang cross-platform compatibility.

## 19. Phân biệt byte-for-byte với functional equivalence

Hai artifact có thể chạy giống nhau nhưng khác bytes. Ví dụ:

- JAR có timestamp entry khác.
- Manifest chứa Build-Time.
- File được nén theo thứ tự khác.
- Generated source chứa đường dẫn workspace.
- Debug metadata ghi thông tin khác.
- Dependency graph thay đổi nhưng code path đang test không sử dụng phần thay đổi.

Functional test chỉ chứng minh hành vi đã kiểm thử tương đương. Nó không chứng minh artifact giống nhau theo byte.

Ngược lại, hai JAR có cùng checksum là bằng chứng mạnh về byte identity, nhưng không tự chứng minh dependency ngoài JAR, runtime image hoặc deployment configuration cũng giống nhau.

Hãy xác định yêu cầu cần đạt:

- **Functional repeatability:** cùng input tạo hành vi đã kiểm thử tương đương.
- **Artifact reproducibility:** cùng input tạo artifact byte-for-byte giống nhau.
- **Environment reproducibility:** môi trường và dependency có thể được tái tạo từ khai báo đã version hóa.
- **Hermeticity:** build không đọc input ngoài danh sách đã khai báo.

Một pipeline có thể theo đuổi nhiều mức cùng lúc, nhưng cần kiểm tra từng mục tiêu bằng phương pháp phù hợp.

## 20. Cấu hình CI để tái tạo môi trường

Một pipeline CI tốt nên:

- Dùng runner image hoặc container image có version rõ ràng.
- Pin image digest khi cần immutable environment.
- Cài JDK đúng vendor/version và xác minh bằng java --version.
- Dùng Wrapper trong repository.
- Chỉ resolve dependency từ repository được phê duyệt.
- Dùng dependency locking và verification.
- Chuẩn hóa locale, timezone và encoding.
- Tạo workspace sạch.
- Không dùng secret hoặc biến build number để thay đổi nội dung artifact ngoài chủ đích.
- Lưu environment manifest, log và artifact checksum.
- Chạy reproducibility check định kỳ hoặc trước release.

Cache giúp giảm thời gian build nhưng không được là nguồn chân lý của dependency/version. Khi cache miss, build vẫn phải resolve đúng dependency đã pin. Khi cache hit, build phải xác minh cache key bao gồm các input quan trọng như Wrapper, JDK/toolchain, dependency lock và OS/architecture nếu có ảnh hưởng.

## 21. Lỗi thường gặp khi kiểm soát môi trường build

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Developer build pass, CI fail | Khác JDK, OS, PATH hoặc environment variable | Ghi manifest và đối chiếu môi trường |
| Cùng commit tạo JAR khác checksum | Timestamp, file order, manifest hoặc generated content thay đổi | Kiểm tra archive entry và generator |
| Build chỉ chạy khi có Internet | Dependency/plugin chưa được cache hoặc khai báo chưa đầy đủ | Pin dependency, chuẩn bị repository mirror và thử offline |
| JDK hiển thị đúng nhưng compiler khác | Toolchain chọn JDK khác JVM chạy build | Kiểm tra javaToolchains và compiler task |
| Resource tiếng Việt bị lỗi | Encoding mặc định khác nhau | Dùng UTF-8 trong source/resource processing |
| Kết quả sort khác nhau giữa máy | Locale hoặc iteration order không xác định | Dùng Locale/Comparator rõ ràng và sort input |
| Timestamp trong JAR thay đổi | Archive hoặc generator dùng wall-clock time | Chuẩn hóa archive timestamp và build metadata |
| Build fail trên Windows | Case sensitivity, path hoặc shell khác | Kiểm tra tên file, path API và script tương thích |
| Build output chứa đường dẫn máy | Generator hoặc compiler ghi absolute path | Dùng relative path và loại bỏ thông tin workspace |
| Task cache trả output cũ | Task thiếu input declaration hoặc đọc env ẩn | Khai báo input/output và environment input |
| Dependency thay đổi dù version không đổi | SNAPSHOT hoặc repository ghi đè artifact | Dùng release immutable, lock và verification |
| Native artifact khác giữa runner | Architecture, compiler hoặc native library khác | Pin platform/toolchain và build riêng theo architecture |
| Log CI vô tình lộ credential | In toàn bộ environment hoặc command chứa secret | Chỉ log whitelist và dùng secret masking |

## 22. Runbook thiết lập môi trường build mới

Khi tạo pipeline cho một dự án Java:

1. Chọn runtime Java tối thiểu và JDK vendor/version.
2. Chọn Gradle/Maven Wrapper tương thích.
3. Cấu hình Java toolchain và --release.
4. Chọn OS/architecture và container image.
5. Chuẩn hóa locale, timezone, charset và line endings.
6. Kiểm soát JAVA_HOME, PATH, JVM options, home/cache và temp directory.
7. Pin plugin/dependency và bật lock/checksum verification.
8. Khai báo generated source và task inputs/outputs đầy đủ.
9. Chuẩn hóa timestamp và archive entry order.
10. Ghi build environment manifest mà không chứa secret.
11. Build cùng commit trong hai workspace sạch.
12. So sánh checksum và điều tra khác biệt nếu có.
13. Lưu log, manifest, checksum và artifact provenance.
14. Lặp lại kiểm tra sau khi nâng JDK, build tool, image hoặc plugin.

## 23. Checklist

- [ ] Đã xác định đầy đủ các thành phần của môi trường build.
- [ ] Đã pin JDK vendor/version hoặc container image chứa JDK.
- [ ] Đã xác minh JDK chạy build và JDK toolchain.
- [ ] Đã pin Gradle/Maven Wrapper và checksum distribution nếu phù hợp.
- [ ] Đã cố định OS, architecture và image digest khi cần.
- [ ] Đã chuẩn hóa locale, UTF-8, timezone và line endings.
- [ ] Đã kiểm tra biến môi trường có thể ảnh hưởng build.
- [ ] Đã tránh in secret vào CI log.
- [ ] Đã kiểm soát dependency, plugin, repository và checksum.
- [ ] Đã khai báo task input/output và generated source rõ ràng.
- [ ] Đã chuẩn hóa timestamp và thứ tự archive entry.
- [ ] Đã dùng workspace sạch và không phụ thuộc file tồn dư.
- [ ] Đã ghi manifest môi trường và Git commit SHA.
- [ ] Đã build cùng commit trong hai môi trường sạch.
- [ ] Đã so sánh SHA-256 và kiểm tra nội dung archive khi khác biệt.
- [ ] Đã lưu artifact provenance và quy trình nâng version.

## 24. Tài liệu tham khảo

- Gradle User Manual — Reproducible Archives: https://docs.gradle.org/current/userguide/working_with_files.html
- Gradle User Manual — Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle User Manual — Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
- Gradle User Manual — Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
- Maven — Reproducible Builds: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- Docker Docs — Image Digests: https://docs.docker.com/dhi/core-concepts/digests/
- Reproducible Builds — SOURCE_DATE_EPOCH: https://reproducible-builds.org/docs/source-date-epoch/
- Git Attributes — End-of-line conversion: https://git-scm.com/docs/gitattributes

Môi trường build reproducible phải được mô tả bằng các đầu vào cụ thể: JDK, Wrapper, plugin/dependency, OS/container, locale, timezone, filesystem và biến môi trường. Khi những đầu vào này được kiểm soát, task khai báo đầy đủ và timestamp/archive được chuẩn hóa, có thể build cùng commit trong hai workspace sạch rồi so sánh checksum để xác nhận artifact có tái tạo được hay không.
# Audit toolchain cho reproducible build

## Mục tiêu

Sau bài này, bạn có thể giải thích toolchain audit là gì và nó hỗ trợ reproducible build ra sao; lập danh sách đầy đủ các đầu vào của một lần build Java; kiểm tra source revision, JDK, compiler, runtime, Gradle/Maven Wrapper, plugin, dependency và môi trường CI; khóa phiên bản dependency và xác minh tính toàn vẹn artifact; chuẩn hóa timestamp, thứ tự file và metadata archive; so sánh artifact giữa hai lần build độc lập; tìm nguyên nhân khi checksum khác nhau; và lưu lại bằng chứng để người khác có thể kiểm tra lại kết quả.

## 1. Toolchain audit là gì?

**Toolchain audit** là việc kiểm kê và xác minh các công cụ, phiên bản, cấu hình và môi trường tham gia tạo ra artifact. Với Java project, toolchain không chỉ là JDK. Nó còn bao gồm:

- Build tool và phiên bản được sử dụng.
- JDK chạy build, compiler, test launcher và Javadoc tool.
- Wrapper, plugin, build extension và build logic.
- Dependency trực tiếp, dependency bắc cầu và annotation processor.
- Repository hoặc mirror cung cấp các artifact.
- Hệ điều hành, kiến trúc CPU, container image và biến môi trường.
- Các bước tạo source/resource, đóng gói, ký và xuất bản artifact.

Audit trả lời câu hỏi: **Lần build này đã sử dụng những đầu vào nào, chúng có được cố định và xác minh hay không, và có thể tái tạo đúng artifact từ cùng source revision hay không?**

Toolchain audit là một phần của quy trình reproducible build. Nó không tự làm cho build trở nên reproducible; nó giúp phát hiện các đầu vào chưa được kiểm soát và cung cấp dữ liệu để khắc phục.

## 2. Reproducible build có nghĩa là gì?

Một build có tính reproducible khi cùng source code, build instructions và môi trường đã xác định có thể được build độc lập để tạo ra artifact giống hệt nhau ở cấp byte.

Ví dụ:

- Build A tạo service.jar có SHA-256 là một fingerprint cụ thể.
- Một agent khác checkout cùng commit và chạy lại build.
- Build B tạo service.jar với cùng SHA-256.
- Khi hai file giống nhau từng byte, checksum của chúng giống nhau.

Nếu hai file có cùng chức năng nhưng byte khác nhau, chúng chưa byte-for-byte reproducible. Có thể khác biệt chỉ do timestamp trong ZIP/JAR, thứ tự entry, manifest, compiler metadata hoặc generated file; vẫn cần điều tra.

### Phân biệt bốn khái niệm

| Khái niệm | Ý nghĩa |
|---|---|
| Repeatable build | Có thể chạy lại build trong cùng môi trường và nhận kết quả ổn định |
| Deterministic build | Cùng tập input đã khai báo luôn tạo cùng output |
| Reproducible build | Một bên độc lập có thể tái tạo artifact từ source và build instructions |
| Hermetic build | Build chỉ đọc các input đã khai báo; không phụ thuộc ngầm vào máy, mạng hoặc trạng thái bên ngoài |

Các khái niệm này liên quan nhưng không đồng nghĩa. Một build có thể repeatable trên máy developer nhưng vẫn phụ thuộc vào thư mục home, cache, file local hoặc JDK chưa được khai báo. Khi chuyển sang máy khác, output có thể thay đổi.

### Vì sao cần audit?

- Điều tra vì sao hai CI runner tạo artifact khác nhau.
- Xác minh artifact phát hành thực sự được tạo từ commit đã review.
- Phát hiện dependency hoặc plugin thay đổi ngoài ý muốn.
- Phân biệt lỗi source với khác biệt do môi trường build.
- Hỗ trợ cache, release approval, rollback và kiểm toán supply chain.
- Cho phép người khác kiểm tra lại artifact đã phát hành.

## 3. Xác định phạm vi audit và artifact cần tái tạo

Trước khi kiểm tra công cụ, xác định chính xác thứ cần audit:

- JAR/WAR/EAR hoặc ZIP nào?
- Một module hay toàn bộ multi-module build?
- Artifact production, test report, Javadoc hay container image?
- Build profile, flavor hoặc feature flag nào?
- Có bước code generation, native compilation, signing hay packaging ngoài Maven/Gradle không?

Một repository có thể tạo nhiều output. Chỉ so sánh một JAR không chứng minh toàn bộ release bundle reproducible nếu image, SBOM, signatures hoặc các module khác vẫn khác nhau.

Ghi lại artifact path và cách định danh. Ví dụ:

| Trường | Giá trị mẫu |
|---|---|
| Repository | payments-service |
| Commit | 4d91... |
| Module | service-core |
| Build command | ./gradlew clean build |
| Artifact | service-core/build/libs/service-core.jar |
| Java release | 17 |
| Compiler toolchain | JDK 21 |
| Build tool | Gradle Wrapper |
| Comparison | SHA-256 và archive contents |

Các giá trị trên chỉ minh họa cấu trúc audit. Khi thực hiện, lấy dữ liệu thực tế từ repository và CI job.

## 4. Bản đồ các đầu vào của Java build

Hãy chia toolchain thành các lớp để tránh chỉ kiểm tra java --version.

| Lớp | Đầu vào cần kiểm tra | Ví dụ bằng chứng |
|---|---|---|
| Source | Commit, branch/tag, dirty tree, submodule, generated source | Git commit, status, submodule SHA |
| Runtime | JDK vendor, feature/patch/build, architecture | java --version, JAVA_HOME |
| Compiler | JDK compiler, release, encoding, annotation processor | javac --version, compiler config |
| Build tool | Gradle/Maven version và Wrapper | Wrapper properties, --version |
| Build logic | Plugin, extension, init script, convention plugin | plugins, pluginManagement, POM |
| Dependency | Direct/transitive versions, lock, checksum | Lockfile, dependency tree |
| Repository | Repository URL, order, mirror, immutable artifact policy | repositories, Maven settings |
| Environment | OS, kernel, libc, architecture, locale, timezone | Runner image, environment manifest |
| Packaging | Archive timestamps, entry order, permissions, manifest | JAR metadata, archive task config |
| Output | Artifact path, size, SHA-256, provenance | Hash file, attestation |

Mỗi đầu vào cần có trạng thái rõ ràng: pinned, verified, recorded, intentionally variable hoặc unknown. Một giá trị chỉ được ghi vào log nhưng không được kiểm soát vẫn có thể thay đổi giữa các lần build.

## 5. Bắt đầu từ source identity

Hai lần build không thể so sánh có ý nghĩa nếu source revision khác nhau hoặc working tree có thay đổi chưa commit.

Kiểm tra:

~~~bash
git rev-parse HEAD
git status --short
git diff --stat
git submodule status
git ls-files
~~~

Cần xác nhận:

1. Commit SHA giống nhau.
2. Working tree không có thay đổi chưa commit.
3. Submodule được checkout đúng commit.
4. Generated source có được tạo từ cùng input/tool version.
5. File LFS đã được tải đúng nội dung nếu repository sử dụng Git LFS.
6. Build không đọc source file nằm ngoài repository mà không khai báo.

### Dirty tree và untracked files

Một build local có thể lấy file chưa commit hoặc untracked file trong khi CI chỉ checkout commit. Hai lần build nhìn cùng commit SHA nhưng input thực tế khác nhau.

Đừng chỉ lưu git rev-parse HEAD. Lưu thêm git status --porcelain và xác nhận build release từ checkout sạch.

### Submodule và Git LFS

Submodule có commit riêng. Ghi lại SHA của từng submodule, không chỉ commit cha. Với Git LFS, Git checkout có thể chứa pointer file nếu object chưa được tải; kiểm tra trạng thái LFS trước build.

### Generated source

Nếu source được tạo từ OpenAPI, Protocol Buffers, ANTLR, schema hoặc template, hãy kiểm soát:

- Phiên bản generator.
- Phiên bản plugin và runtime.
- Input schema.
- Thứ tự input files.
- Locale, timezone và timestamp mà generator sử dụng.
- Có commit generated source hay tạo lại trong CI.

Nếu generated source được commit nhưng CI vẫn regenerate, cần xác định output nào thực sự được compile.

## 6. Audit JDK và Java compiler

JDK là một trong những đầu vào quan trọng nhất vì compiler version có thể ảnh hưởng tới bytecode và metadata trong artifact.

Ghi lại tối thiểu:

- JDK vendor/distribution.
- Feature release.
- Patch/build number.
- Architecture.
- JAVA_HOME.
- Java runtime được PATH tìm thấy.
- Compiler được build tool lựa chọn.
- JDK dùng để chạy test và Javadoc.
- Các compiler flag như --release, encoding, debug info và annotation processor.

Lệnh kiểm tra:

~~~bash
echo "$JAVA_HOME"
command -v java
command -v javac
java --version
javac --version
java -XshowSettings:properties -version
~~~

java -XshowSettings:properties -version có thể hiển thị java.vendor, java.version, java.home, os.arch, file.encoding và user.timezone.

Trên Windows PowerShell:

~~~powershell
Write-Output $env:JAVA_HOME
where.exe java
where.exe javac
java --version
javac --version
Get-Command java | Format-List Source
Get-Command javac | Format-List Source
~~~

### Phân biệt build JVM và compiler toolchain

Gradle daemon có thể chạy bằng một JDK nhưng task compile, test hoặc Javadoc dùng toolchain khác. Maven cũng có thể chạy bằng một JDK trong khi Maven Toolchains Plugin chọn JDK khác cho compiler plugin.

Vì vậy, chỉ ghi java --version chưa đủ. Cần kiểm tra cả:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
mvn --version
~~~

Chạy lệnh tương ứng với build tool đang dùng. javaToolchains liệt kê các JDK/JRE Gradle phát hiện, cùng vendor, architecture và nguồn phát hiện.

### Pin toolchain trong Gradle

Ví dụ Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Cấu hình này yêu cầu JDK 21 thuộc vendor Adoptium cho Java tasks và giới hạn API/bytecode ở Java 17.

languageVersion và vendor chưa nhất thiết pin chính xác patch/build của JDK. Nếu yêu cầu byte-for-byte reproducibility nghiêm ngặt, hãy kiểm soát JDK image/archive cụ thể và ghi lại digest hoặc checksum của package.

### --release có vai trò gì?

--release 17 yêu cầu compiler:

- Dùng quy tắc ngôn ngữ của Java 17.
- Tạo class file tương thích Java 17.
- Chỉ compile dựa trên API được cung cấp trong Java 17.

Nó không chọn compiler JDK và không biến hai compiler version khác nhau thành cùng một compiler. Hãy pin JDK toolchain và đặt --release riêng để kiểm soát cả compiler lẫn compatibility target.

### Maven toolchain

Maven Toolchains Plugin cho phép project yêu cầu một JDK cụ thể đã được cài trên agent. File ~/.m2/toolchains.xml ánh xạ requirement sang JDK home.

Ví dụ cấu hình toolchain:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdk/temurin-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

Đường dẫn là ví dụ và phải khớp JDK thực tế trên agent. Toolchain chọn JDK đã có; nó không tự cài JDK. Kiểm tra version/vendor được POM yêu cầu có khớp entry không.

### Annotation processors

Annotation processor là code chạy trong compile phase. Lombok, MapStruct và processor nội bộ có thể tạo source/class output.

Audit cả version processor, dependency transitives và option truyền vào processor. Nếu processor đọc thời gian, filesystem, biến môi trường hoặc thứ tự file, nó có thể làm output thay đổi.

## 7. Audit Gradle Wrapper và Maven Wrapper

Wrapper cố định build tool version cho developer và CI. Build tool cài sẵn trên máy không nên quyết định version thực thi.

### Gradle Wrapper

Các file quan trọng:

~~~text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
~~~

Kiểm tra:

- distributionUrl trỏ tới đúng Gradle release và dùng HTTPS.
- Version được pin cụ thể, không trỏ tới URL động.
- distributionSha256Sum có giá trị SHA-256 lấy từ nguồn phát hành chính thức.
- Wrapper JAR trong repository khớp checksum hoặc signature chính thức.
- Wrapper files được commit vào source control.
- Thay đổi Wrapper được review như một thay đổi supply chain.

distributionSha256Sum xác minh file ZIP của Gradle distribution khi tải. Nó không tự xác minh Wrapper JAR đã commit. Wrapper JAR cần được xác minh riêng theo checksum/signature chính thức.

Có thể kiểm tra version bằng:

~~~bash
./gradlew --version
~~~

Đừng chạy Wrapper của repository chưa tin cậy trước khi kiểm tra wrapper JAR, distribution URL, checksum và build logic. Wrapper chạy trước phần lớn cơ chế bảo vệ do project tự cấu hình.

### Maven Wrapper

Các file thường gặp:

~~~text
mvnw
mvnw.cmd
.mvn/wrapper/maven-wrapper.properties
.mvn/wrapper/maven-wrapper.jar
~~~

Kiểm tra:

- distributionUrl trỏ tới Maven release cụ thể.
- URL và repository mirror được tin cậy.
- distributionSha256Sum xác minh Maven distribution.
- wrapperSha256Sum xác minh Maven Wrapper JAR nếu distribution sử dụng file JAR đó.
- Wrapper script và properties được commit.
- Wrapper download không lấy snapshot hoặc artifact mutable cho release build.

Chạy:

~~~bash
./mvnw --version
~~~

Maven Wrapper hỗ trợ repository manager nội bộ. Khi dùng mirror, kiểm tra mirror trả cùng nội dung artifact như nguồn đã xác minh.

### Vì sao Wrapper checksum quan trọng?

Pin URL chỉ xác định nơi tải. Checksum xác minh bytes nhận được có khớp với artifact dự kiến hay không.

Lấy checksum từ trang phát hành hoặc metadata độc lập của vendor. Không tính hash của file vừa tải rồi dùng chính hash đó làm bằng chứng tin cậy; thao tác đó chỉ chứng minh bạn có thể hash file, không chứng minh file là bản phát hành chính thức.

## 8. Audit plugin và build logic

Build plugin là code thực thi trong quá trình build. Nó có thể thay đổi dependency, tạo file, sửa manifest hoặc tải công cụ phụ.

### Gradle

Kiểm tra:

- Plugin version trong plugins block.
- pluginManagement trong settings.gradle(.kts).
- Buildscript classpath.
- Convention plugins và buildSrc.
- Included builds.
- Init script trong Gradle User Home.
- Repository dùng để resolve plugin.
- Plugin tự tải tool hoặc chạy process ngoài.

Tránh plugin version động như latest.release, version range hoặc snapshot trong release build. Pin version đã review.

Một plugin có thể có dependency graph riêng. Lock dependency project không tự động đồng nghĩa mọi build logic/plugin resolution đều đã được khóa. Xem xét riêng buildscript classpath và plugin repositories.

### Maven

Kiểm tra:

- Plugin version trong POM.
- pluginManagement ở parent POM.
- Maven core extension trong .mvn/extensions.xml.
- Profile được bật theo environment.
- settings.xml và mirror.
- Plugin dependency và build extension.
- Plugin nào chạy ở lifecycle phase tạo artifact.

Không dựa vào Maven mặc định chọn version plugin nếu mục tiêu là reproducible build. Pin plugin version trong parent POM hoặc pluginManagement và kiểm tra effective POM.

### Build logic từ xa

Một script tải qua HTTP URL hoặc build step tải executable không được pin có thể thay đổi mà không có source commit mới.

Ghi lại hoặc loại bỏ các nguồn build logic ngoài repository. Với script cần tải, pin version, checksum/signature và URL tin cậy. Không chạy lệnh kiểu tải script rồi pipe thẳng vào shell trong release pipeline.

## 9. Audit dependency graph

Một dependency coordinate gồm group, artifact và version. Cùng version string vẫn có thể trả về bytes khác nhau nếu repository cho phép ghi đè artifact hoặc dùng snapshot/changing module.

Cần kiểm tra:

- Direct dependencies.
- Transitive dependencies.
- Plugin dependencies.
- Annotation processor.
- Test dependencies.
- Build logic dependencies.
- Version catalog/BOM.
- Repository order, mirror và content filtering.
- Artifact có immutable release policy hay không.

### Gradle dependency locking

Gradle hỗ trợ lưu resolved dependency version vào lockfile. Ví dụ:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Sinh hoặc cập nhật lock state:

~~~bash
./gradlew dependencies --write-locks
~~~

Lockfile mặc định tên gradle.lockfile và nên được commit. Mỗi project/subproject có thể có lock state riêng.

Locking cố định version được resolve, bao gồm transitive dependencies. Nó không cố định bytes của một changing dependency như SNAPSHOT; cùng coordinates có thể trả về nội dung khác nhau. Không coi dependency locking là thay thế cho artifact checksum verification.

Lưu ý: lockAllConfigurations() không tự khóa buildscript classpath. Nếu dùng script plugin/buildscript dependencies, hãy audit và cấu hình locking cho classpath đó theo yêu cầu project.

### Gradle dependency verification

Dependency verification kiểm tra checksum hoặc signature của dependency/plugin đã tải.

Sinh metadata từ dependency hiện tại:

~~~bash
./gradlew --write-verification-metadata sha256
~~~

Nếu muốn ghi checksum và PGP signature khi có:

~~~bash
./gradlew --write-verification-metadata sha256,pgp
~~~

File được tạo tại:

~~~text
gradle/verification-metadata.xml
~~~

Sau khi metadata tồn tại, Gradle xác minh artifact trong các lần build tiếp theo. Nếu checksum không khớp hoặc metadata thiếu, build sẽ fail.

**Bootstrap cần review:** lệnh sinh metadata lấy artifact từ repository hiện tại và ghi checksum của chúng. Nếu repository đã bị compromise hoặc dependency sai đã được resolve, file mới có thể vô tình tin cậy artifact đó. Xác minh nguồn và diff metadata trước khi commit.

Checksum xác nhận bytes không thay đổi so với giá trị tin cậy. Signature giúp xác minh artifact được ký bởi key cụ thể; key đó vẫn phải được tin cậy qua quy trình review.

### Maven dependency audit

Maven thường quản lý version qua dependency declaration, parent POM, BOM và dependencyManagement. Để audit resolved graph, chạy:

~~~bash
mvn dependency:tree -Dverbose
mvn help:effective-pom
~~~

Kiểm tra:

- Có dependency version range không.
- Có SNAPSHOT hoặc version mutable không.
- Parent POM/BOM có được pin không.
- Dependency bắc cầu có bị override ngoài ý muốn không.
- Plugin version có cố định không.
- Repository order có làm thay đổi nguồn artifact không.
- Internal repository có immutable release policy không.

dependencyManagement giúp quản lý version tập trung; nó không tự chứng minh bytes artifact bất biến. Với Maven, hãy lưu dependency tree/effective POM của release và áp dụng policy version rõ ràng. Nếu tổ chức dùng thêm lock hoặc verification tooling, audit cả file và bước xác minh đó.

### Không dùng version động trong release build

Ví dụ nên tránh trong release:

~~~groovy
dependencies {
    implementation 'org.example:library:1.+'
}
~~~

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>library</artifactId>
    <version>[1.0,2.0)</version>
</dependency>
~~~

Build hôm nay và tháng sau có thể resolve version khác dù source không đổi. Hãy dùng version cố định và lock resolved graph.

## 10. Audit repository và artifact origin

Một dependency version cố định chưa đủ nếu repository cho phép ghi đè cùng coordinates.

Audit:

- URL repository và protocol.
- Thứ tự ưu tiên repository.
- Maven mirror và Gradle repository content filter.
- Có repository nội bộ proxy/cache hay không.
- Snapshot/release policy.
- Artifact có được phép redeploy sau publish không.
- Plugin repository có tách khỏi library repository không.
- Credentials có được truyền an toàn và không ghi vào log không.

Đối với release build, ưu tiên repository quản lý có chính sách immutable release artifact. Nếu cần mirror nội bộ, lưu cấu hình mirror và kiểm tra checksum artifact sau khi tải.

Không để dependency resolution phụ thuộc vào repository public/private được thêm ngẫu nhiên bởi máy developer hoặc init script không nằm trong audit manifest.

## 11. Audit môi trường hệ điều hành và CI runner

Cùng JDK version vẫn có thể build khác nhau do môi trường.

Ghi lại:

| Thành phần | Ví dụ cần ghi |
|---|---|
| OS | Ubuntu, Windows Server, macOS |
| Kernel | Kernel version |
| CPU | x86_64, ARM64 |
| libc | glibc/musl và version nếu có native tool |
| Container | Image tag và immutable digest |
| Filesystem | Case sensitivity, file permissions |
| Locale | LANG, LC_ALL |
| Timezone | TZ, timezone của process |
| Charset | file.encoding |
| Line ending | LF hoặc CRLF |
| Working directory | Đường dẫn workspace |
| Environment | Chỉ các biến ảnh hưởng build đã được cho phép |

Nếu build dùng GraalVM Native Image, JNI, C/C++ compiler hoặc native library, audit thêm compiler/linker, SDK, libc và native toolchain. JDK version một mình không mô tả đủ môi trường tạo native binary.

### Locale, timezone và encoding

Build có thể phụ thuộc vào:

- Sắp xếp chuỗi theo locale.
- Parse/format date theo timezone.
- Charset mặc định của JVM.
- Line ending của file được checkout.
- Locale-sensitive code generation.

Đặt locale/timezone/encoding rõ ràng nếu build cần chúng. Ví dụ:

~~~bash
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export TZ=UTC
~~~

Cần xác nhận locale C.UTF-8 có tồn tại trên runner. Với Windows, dùng cấu hình locale tương ứng OS và kiểm tra charset của JVM.

Không ghi toàn bộ env vào artifact audit. CI environment có thể chứa token, password hoặc credential. Chỉ ghi allowlist các biến không nhạy cảm có ảnh hưởng build.

## 12. Audit archive và generated metadata

Ngay cả khi class file giống nhau, JAR/ZIP có thể khác byte do metadata đóng gói.

Các nguồn khác biệt phổ biến:

- Timestamp của entry trong archive.
- Thứ tự entry.
- File permission.
- Manifest có build timestamp hoặc hostname.
- Build metadata chứa absolute path hoặc username.
- Generated resource có timestamp.
- Resource filtering chèn biến môi trường.
- File order phụ thuộc filesystem traversal.
- Line ending hoặc encoding của resource.

### Gradle archive tasks

Từ Gradle 9.0, archive tasks như Jar, Zip, War và Ear tạo archive reproducible theo mặc định:

- File entry có thứ tự xác định.
- Timestamp của entry được cố định theo loại archive.
- Directory/file permissions được chuẩn hóa.

Với Gradle cũ, có thể cấu hình rõ:

~~~groovy
tasks.withType(org.gradle.api.tasks.bundling.AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Không bật lại preserve timestamps hoặc filesystem iteration order nếu mục tiêu là reproducible archive. Kiểm tra plugin đóng gói tùy chỉnh vì plugin đó có thể tự tạo archive ngoài các task chuẩn.

### Maven output timestamp

Maven hướng dẫn dùng property project.build.outputTimestamp và plugin có hỗ trợ reproducible build.

Ví dụ trong POM:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.outputTimestamp>2025-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Timestamp là giá trị ổn định được quản lý trong source control. Một số dự án dùng timestamp của commit cuối cùng, nhưng cần bảo đảm cách lấy timestamp ổn định và chuẩn hóa UTC.

Property này chỉ có tác dụng với plugin hỗ trợ reproducible output. Hãy kiểm tra từng plugin tạo JAR, source archive, Javadoc, assembly hoặc report.

### Manifest và build metadata

Kiểm tra META-INF/MANIFEST.MF và resource generated có chứa:

- Build-Time.
- Build-Host.
- User name.
- Workspace path.
- Current date/time.
- Random identifier.
- Tool version hoặc commit metadata.

Một số metadata là yêu cầu sản phẩm. Nếu cần giữ chúng, chọn giá trị deterministic, ví dụ commit SHA và timestamp đã chuẩn hóa từ source revision, thay vì giờ thực tế của runner.

### SOURCE_DATE_EPOCH

SOURCE_DATE_EPOCH là convention được một số build tool/plugin sử dụng để chuẩn hóa timestamp. Không phải mọi Java compiler, Maven plugin hoặc Gradle plugin đều tự động đọc biến này.

Chỉ dựa vào biến đó khi xác nhận plugin cụ thể hỗ trợ. Với Maven, project.build.outputTimestamp là cơ chế được tài liệu Maven hướng dẫn; với Gradle, dùng archive task properties phù hợp.

## 13. Audit Gradle build configuration

Một cấu hình Gradle audit nên kiểm tra:

~~~text
gradle/wrapper/gradle-wrapper.properties
gradle/wrapper/gradle-wrapper.jar
settings.gradle hoặc settings.gradle.kts
build.gradle hoặc build.gradle.kts
gradle.properties
gradle/libs.versions.toml
gradle.lockfile
gradle/verification-metadata.xml
buildSrc/
build-logic/
~~~

### Kiểm tra plugin và version catalog

- Plugin version có pin không?
- Version catalog có version range hoặc alias thay đổi không?
- Convention plugin có dependency không được khai báo không?
- Included build có wrapper/build logic riêng không?
- Init script trong Gradle User Home có can thiệp repository hoặc toolchain không?

### Kiểm tra task input

Task custom phải khai báo input/output đúng. Nếu task đọc file ngoài project, environment variable hoặc service response nhưng không khai báo, Gradle có thể cho rằng output vẫn up-to-date khi input thực tế đã thay đổi.

Đừng nhầm build cache hit với bằng chứng reproducibility. Cache trả output đã tạo trước; để audit byte-for-byte, cần có lần build độc lập không dựa vào output cache.

### Lệnh audit Gradle hữu ích

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew dependencies
./gradlew dependencyInsight --dependency guava --configuration runtimeClasspath
./gradlew tasks --all
~~~

Thay guava và configuration bằng dependency thực tế. Multi-project build cần chạy audit ở từng module/configuration quan trọng.

## 14. Audit Maven build configuration

Kiểm tra các file:

~~~text
.mvn/wrapper/maven-wrapper.properties
.mvn/wrapper/maven-wrapper.jar
.mvn/extensions.xml
.mvn/maven.config
pom.xml
parent-pom.xml
settings.xml
toolchains.xml
~~~

Một số file nằm trong home hoặc CI secret store thay vì repository. Audit cần ghi lại file/configuration nào được sử dụng, nhưng không được xuất credential.

### Effective POM

POM cuối cùng có thể kế thừa từ parent, BOM và profile. Vì vậy, đọc một POM con chưa đủ.

~~~bash
mvn help:effective-pom
mvn help:active-profiles
mvn dependency:tree -Dverbose
mvn --version
~~~

Lưu output phù hợp cho audit, lọc credential hoặc repository URL có thông tin đăng nhập trước khi upload.

### Pin plugin

Đặt plugin version trong parent POM hoặc pluginManagement, đặc biệt các plugin tạo artifact:

- Maven Compiler Plugin.
- Maven Resources Plugin.
- Maven JAR/WAR Plugin.
- Maven Surefire/Failsafe.
- Maven Assembly/ Shade.
- Source/Javadoc plugin.
- Plugin tạo build info hoặc generated source.

Mỗi plugin có thể có behavior reproducibility khác nhau. Dùng mvn artifact:check-buildplan để kiểm tra plugin nào cần nâng lên phiên bản hỗ trợ reproducible build.

## 15. Chuẩn hóa dependency và build logic

Một toolchain audit nên đánh giá cả version stability và content integrity.

| Kiểm soát | Điều nó chứng minh |
|---|---|
| Wrapper version pin | Build dùng đúng Gradle/Maven version |
| JDK toolchain pin | Compile/test dùng JDK theo yêu cầu |
| Dependency lock | Dependency resolution dùng đúng version |
| Dependency verification | Artifact bytes/signature khớp metadata tin cậy |
| Plugin version pin | Build logic dùng plugin version đã review |
| Repository policy | Artifact lấy từ nguồn được kiểm soát |
| Container digest | Runner image có nội dung bất biến |
| Artifact checksum | Output bytes có thể so sánh |
| Attestation | Có bằng chứng về workflow/source đã tạo artifact |

Không có một kiểm soát nào thay thế toàn bộ các kiểm soát còn lại. Ví dụ lockfile cố định version nhưng không phát hiện repository trả JAR bị thay đổi; checksum cố định bytes nhưng không chứng minh version đó an toàn.

## 16. Tạo audit manifest cho một lần build

Audit manifest là bản ghi ngắn gọn các đầu vào thực tế. Nó nên được lưu cùng CI artifact hoặc release metadata.

Một manifest tối thiểu có thể gồm:

~~~text
source.commit=4d91...
source.dirty=false
source.submodules=recorded
build.tool=Gradle Wrapper
build.version=9.9
build.wrapper.sha256=recorded
jdk.vendor=Eclipse Adoptium
jdk.version=21.0.x
jdk.arch=x86_64
compiler.release=17
os.image=ubuntu-24.04@sha256:...
locale=C.UTF-8
timezone=UTC
dependency.lock=present
dependency.verification=enabled
artifact.path=build/libs/service.jar
artifact.sha256=...
~~~

Các giá trị trên chỉ minh họa định dạng. Manifest thật phải được tạo từ lệnh kiểm tra trên runner và không được ghi credential.

### Lệnh kiểm tra nhanh trên Linux

~~~bash
set -e

echo "SOURCE"
git rev-parse HEAD
git status --short
git submodule status || true

echo "SYSTEM"
uname -a
uname -m
printf 'LANG=%s\n' "$LANG"
printf 'LC_ALL=%s\n' "$LC_ALL"
printf 'TZ=%s\n' "$TZ"

echo "JAVA"
echo "JAVA_HOME=$JAVA_HOME"
java --version
javac --version
java -XshowSettings:properties -version 2>&1

echo "BUILD TOOLS"
if [ -x ./gradlew ]; then
  ./gradlew --version
  ./gradlew -q javaToolchains
fi

if [ -x ./mvnw ]; then
  ./mvnw --version
fi
~~~

Nếu biến locale hoặc JAVA_HOME chưa được đặt, shell có thể in giá trị rỗng. Audit phải coi đó là dữ liệu cần điều tra thay vì tự suy ra version mong muốn.

### Hash Wrapper và artifact

Linux:

~~~bash
sha256sum gradle/wrapper/gradle-wrapper.jar
sha256sum .mvn/wrapper/maven-wrapper.jar
sha256sum build/libs/*.jar
~~~

Chỉ chạy hash cho file thực sự tồn tại. Với project không dùng một Wrapper hoặc không tạo JAR ở đường dẫn đó, bỏ lệnh tương ứng.

Windows PowerShell:

~~~powershell
Get-FileHash gradle\wrapper\gradle-wrapper.jar -Algorithm SHA256
Get-FileHash .mvn\wrapper\maven-wrapper.jar -Algorithm SHA256
Get-FileHash build\libs\*.jar -Algorithm SHA256
~~~

Hash local chỉ cung cấp fingerprint để so sánh. Để xác minh Wrapper hoặc dependency, so sánh với checksum/signature từ nguồn phát hành độc lập đã được tin cậy.

## 17. Thực hiện hai lần build độc lập

Một quy trình kiểm chứng cơ bản:

1. Chọn commit đã xác định và checkout sạch.
2. Dùng cùng wrapper, JDK toolchain, plugin, dependency lock và verification metadata.
3. Chuẩn hóa environment, locale, timezone, encoding và container image.
4. Build sạch, tránh reuse build output cũ.
5. Lưu artifact và SHA-256 của lần đầu.
6. Checkout cùng commit ở workspace/agent khác.
7. Lặp lại build với cùng inputs.
8. So sánh checksum và nội dung archive.
9. Nếu khác, dùng công cụ diff để tìm entry hoặc file khác.
10. Lưu manifest và kết quả so sánh.

### Build Gradle

~~~bash
./gradlew clean build --no-build-cache
sha256sum build/libs/*.jar
~~~

--no-build-cache giúp tránh lấy task output từ build cache trong phép thử này. Dependency cache vẫn có thể được dùng; dependency integrity cần được kiểm soát riêng bằng lock và verification metadata.

### Build Maven

~~~bash
./mvnw --batch-mode clean verify
sha256sum target/*.jar
~~~

Với multi-module project, chọn đúng artifact path cho từng module. Đảm bảo profile, Maven settings, toolchain và repository mirror giống nhau.

### Maven artifact compare

Maven cung cấp maven-artifact-plugin để so sánh hai lần build:

~~~bash
mvn clean install
mvn clean verify artifact:compare
~~~

Lệnh thứ hai rebuild project rồi so sánh output với reference đã install. Kiểm tra report để biết artifact nào khác.

Phép thử trên cùng một máy phát hiện được một số vấn đề như timestamp, nhưng chưa chứng minh reproducibility giữa hai bên độc lập. Muốn kiểm chứng mạnh hơn, hãy rebuild trên máy/container khác với workspace và user khác.

### So sánh checksum

Linux:

~~~bash
sha256sum build-a/service.jar
sha256sum build-b/service.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash build-a\service.jar -Algorithm SHA256
Get-FileHash build-b\service.jar -Algorithm SHA256
~~~

Cùng checksum là bằng chứng hai file giống nhau từng byte với xác suất va chạm SHA-256 cực thấp. Khác checksum nghĩa là cần điều tra; nó chưa tự chỉ ra lỗi nằm ở source, compiler hay packaging.

## 18. Điều tra khi checksum khác nhau

Đừng sửa ngẫu nhiên nhiều cấu hình cùng lúc. So sánh từng lớp input và tìm file/entry đầu tiên khác nhau.

### Bước 1: so sánh archive metadata

Liệt kê nội dung:

~~~bash
unzip -l build-a/service.jar
unzip -l build-b/service.jar
~~~

Kiểm tra thứ tự entry, timestamp, kích thước và tên file. Nếu chỉ metadata ZIP khác nhau, tìm plugin tạo archive hoặc resource filtering liên quan.

### Bước 2: so sánh manifest

~~~bash
unzip -p build-a/service.jar META-INF/MANIFEST.MF
unzip -p build-b/service.jar META-INF/MANIFEST.MF
~~~

Tìm build timestamp, build host, JDK version, commit metadata hoặc trường do plugin thêm vào.

### Bước 3: so sánh class file

Giải nén hai archive vào hai thư mục riêng, rồi so sánh:

~~~bash
mkdir -p /tmp/build-a /tmp/build-b
unzip -q build-a/service.jar -d /tmp/build-a
unzip -q build-b/service.jar -d /tmp/build-b
diff -ru /tmp/build-a /tmp/build-b
~~~

Nếu class file khác, kiểm tra compiler JDK, compiler flags, annotation processor, generated source, debug metadata và dependency classpath.

### Bước 4: dùng diffoscope

diffoscope có thể mở sâu JAR, ZIP, TAR và nhiều định dạng khác để chỉ ra phần khác nhau. Công cụ này hữu ích khi checksum khác nhưng binary diff không dễ đọc.

Với Maven, artifact:buildinfo có thể đề xuất command diffoscope cho artifact không khớp.

### Bước 5: kiểm tra environment leak

Tìm các giá trị được nhúng từ:

- Username và home directory.
- Workspace absolute path.
- Hostname và IP.
- Current time hoặc timezone.
- Locale và charset.
- Environment variable.
- File system iteration order.
- Random number hoặc UUID.
- Network response hoặc remote API.
- Dependency/plugin được resolve khác nhau.

Sau khi tìm ra nguồn, chỉ thay đổi một yếu tố và chạy lại cả hai build.

## 19. Những nguyên nhân không reproducible thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| JAR hash thay đổi mỗi lần | Timestamp trong ZIP/JAR | Archive timestamp và outputTimestamp |
| Entry order khác nhau | File traversal không deterministic | Reproducible file order |
| Class file khác | JDK/compiler hoặc processor khác | Toolchain, javac, compiler flags |
| Dependency tree khác | Dynamic version, snapshot, repository | Lockfile, effective POM, dependency tree |
| Manifest khác | Build time, hostname, git metadata | Packaging plugin và generated metadata |
| Chỉ CI khác local | Runner image, locale, timezone, path | Audit manifest và container digest |
| Chỉ một module khác | Plugin/module-specific config | Task graph, plugin version, module lock |
| Artifact khác khi offline/online | Remote metadata hoặc dependency mới | Repository, metadata cache, snapshots |
| Build pass nhưng checksum khác | Nondeterministic output | Diffoscope và archive entry diff |
| Build chỉ pass khi có cache | Input bị thiếu hoặc task không khai báo input | Task input/output và clean build |

### Snapshot và changing dependency

Một SNAPSHOT hoặc changing module có thể giữ nguyên version coordinate nhưng thay đổi bytes. Lock version không thể cố định nội dung thay đổi theo thời gian.

Release build nên dùng immutable release artifacts và verification metadata phù hợp.

### Plugin không reproducible

Một plugin có thể chèn timestamp, hostname hoặc thứ tự file không ổn định. Maven artifact:check-buildplan giúp phát hiện plugin cần nâng cấp để hỗ trợ reproducible output.

Với Gradle, kiểm tra plugin archive/task behavior và input/output declaration của task custom.

### Absolute path và user home

Một plugin có thể ghi đường dẫn workspace vào generated source, manifest hoặc build info. Hai runner có workspace path khác nhau sẽ tạo output khác.

Chuẩn hóa working directory nếu plugin hỗ trợ; tốt hơn là sửa plugin để chỉ ghi path tương đối hoặc loại bỏ path khỏi artifact nếu không cần.

## 20. Build cache không chứng minh reproducibility

Build cache giúp tái sử dụng output của task khi input được xem là giống nhau. Nó có thể che giấu task không khai báo đủ input hoặc output đã được tạo từ một môi trường khác.

Trong audit:

- Chạy một build clean không dùng build cache.
- So sánh build output được tạo độc lập.
- Kiểm tra task custom khai báo input/output.
- Không coi cache hit là bằng chứng artifact có thể được rebuild độc lập.
- Không xóa dependency integrity metadata chỉ để làm cache hit.

Dependency cache và build cache cũng khác nhau. Dependency cache lưu thư viện tải về; build cache lưu output của task. Cả hai cần chính sách riêng.

## 21. Provenance, checksum, SBOM và reproducibility

Các bằng chứng sau trả lời những câu hỏi khác nhau:

| Bằng chứng | Câu hỏi trả lời |
|---|---|
| SHA-256 artifact | File này có đúng bytes như fingerprint đã ghi không? |
| Dependency verification | Dependency/plugin tải về có đúng bytes/key được tin cậy không? |
| SBOM | Artifact được tạo từ những component/dependency nào? |
| Build provenance/attestation | Artifact được tạo bởi repository, commit, workflow và môi trường nào? |
| Independent rebuild | Bên khác có tái tạo được cùng artifact từ source và build instructions không? |

Một attestation hợp lệ không tự chứng minh artifact reproducible. Nó cung cấp bằng chứng về nơi và cách artifact được tạo. Một checksum không tự chứng minh artifact an toàn; nó chỉ xác định nội dung file.

GitHub Actions có thể tạo artifact attestation để ghi nhận workflow, repository, commit SHA, event và artifact digest. Với binary, workflow có thể dùng actions/attest sau khi build artifact. Quyền và phạm vi sử dụng phụ thuộc loại repository và plan GitHub.

## 22. Ví dụ cấu hình Gradle cho reproducible build

Một ví dụ kết hợp toolchain, release target, dependency locking và archive behavior:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

dependencyLocking {
    lockAllConfigurations()
}

tasks.withType(org.gradle.api.tasks.bundling.AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Để hoàn thiện cấu hình, cần:

1. Pin Gradle Wrapper version và checksum.
2. Pin plugin version trong build/settings.
3. Tạo và commit lockfile.
4. Tạo và review dependency verification metadata.
5. Kiểm tra cả buildscript/plugin classpath.
6. Chuẩn hóa locale/timezone và runner image.
7. Audit các task custom và generated file.
8. Chạy independent rebuild rồi so sánh artifact.

Ví dụ chỉ minh họa các cơ chế chính. Project thật có thể cần cấu hình thêm test launcher, Javadoc tool, annotation processor và native toolchain.

## 23. Ví dụ cấu hình Maven cho reproducible build

Một phần POM:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.build.outputTimestamp>2025-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>

<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

POM thật cần pin version cho các plugin tham gia build, không chỉ compiler plugin. Chọn timestamp ổn định theo release policy; kiểm tra các plugin tạo output có hỗ trợ reproducible build hay không.

Các lệnh audit hữu ích:

~~~bash
./mvnw --version
./mvnw help:effective-pom
./mvnw help:active-profiles
./mvnw dependency:tree -Dverbose
./mvnw artifact:check-buildplan
~~~

Sau khi xử lý plugin chưa hỗ trợ, thử:

~~~bash
./mvnw clean install
./mvnw clean verify artifact:compare
~~~

So sánh lại trên workspace/agent khác để kiểm chứng độc lập.

## 24. Quy trình audit toolchain theo từng giai đoạn

### Giai đoạn A — Inventory

1. Xác định artifact và build command.
2. Ghi commit, dirty tree, submodule và generated source.
3. Ghi JDK vendor/version/architecture.
4. Ghi compiler, test và Javadoc toolchain.
5. Ghi Gradle/Maven Wrapper version và checksum.
6. Ghi plugin, extension và build logic.
7. Ghi dependency graph, repository và lock/verification files.
8. Ghi OS/container image, locale, timezone và encoding.

### Giai đoạn B — Pin và verify

1. Pin Wrapper version và xác minh checksum.
2. Pin JDK toolchain phù hợp.
3. Khóa resolved dependency versions.
4. Xác minh checksum/signature dependency.
5. Pin plugin và build extension version.
6. Dùng immutable repository artifacts.
7. Chuẩn hóa environment và archive metadata.
8. Review task custom và generated output.

### Giai đoạn C — Independent rebuild

1. Tạo hai checkout sạch cùng commit.
2. Dùng cùng container/toolchain hoặc môi trường đã mô tả.
3. Build sạch và tránh reuse task output cache.
4. Lưu artifact, SHA-256 và manifest.
5. So sánh hash.
6. Mở archive và so sánh entry nếu hash khác.
7. Dùng diffoscope để tìm khác biệt sâu.
8. Sửa từng nguồn nondeterminism và lặp lại.

### Giai đoạn D — Lưu bằng chứng

1. Lưu audit manifest.
2. Lưu dependency tree/lockfile và verification metadata.
3. Lưu build logs và tool versions.
4. Lưu artifact checksums.
5. Lưu kết quả independent rebuild.
6. Lưu SBOM/attestation nếu pipeline có hỗ trợ.
7. Gắn kết quả audit với commit và release ID.

## 25. Mẫu báo cáo audit

| Nhóm | Kết quả quan sát | Trạng thái | Bằng chứng |
|---|---|---|---|
| Source revision | Commit và dirty state | PASS/FAIL | Git SHA/status |
| JDK | Vendor/version/architecture | PASS/FAIL | Runtime/compiler output |
| Toolchain | Compiler/test/Javadoc | PASS/FAIL | Toolchain report |
| Wrapper | Version và checksum | PASS/FAIL | Wrapper properties/hash |
| Plugins | Version cố định | PASS/FAIL | Effective POM/build files |
| Dependencies | Lock và verification | PASS/FAIL | Lockfile/metadata |
| Repository | Nguồn artifact ổn định | PASS/FAIL | Repository config |
| Environment | OS/image/locale/timezone | PASS/FAIL | CI manifest |
| Packaging | Timestamp/order/permissions | PASS/FAIL | Archive config |
| Rebuild | Hai artifact cùng SHA-256 | PASS/FAIL | Hash comparison |
| Provenance | Commit/workflow/artifact linked | PASS/FAIL | Attestation |

Không đánh dấu PASS chỉ vì một file cấu hình tồn tại. Hãy kiểm tra build thực tế đã sử dụng đúng file/cấu hình đó.

## 26. Checklist trước khi phát hành

### Source và build tool

- [ ] Commit SHA được ghi lại.
- [ ] Working tree sạch.
- [ ] Submodule/LFS/generated source được xác minh.
- [ ] Gradle/Maven Wrapper được dùng thay cho build tool tùy ý trên PATH.
- [ ] Wrapper distribution và Wrapper JAR được xác minh checksum/signature.
- [ ] Plugin và build extension version được pin.

### Java toolchain

- [ ] JDK vendor, version, patch/build và architecture được ghi lại.
- [ ] JDK chạy build được phân biệt với compiler/test/Javadoc toolchain.
- [ ] Compiler --release được cấu hình đúng.
- [ ] Annotation processor version được pin.
- [ ] Java toolchain được phát hiện đúng trên CI.

### Dependency và repository

- [ ] Không có version range hoặc dynamic version ngoài policy.
- [ ] Không có SNAPSHOT/changing dependency trong release build.
- [ ] Transitive dependency graph được kiểm tra.
- [ ] Gradle lockfile hoặc Maven dependency management được quản lý.
- [ ] Dependency checksum/signature được xác minh.
- [ ] Repository/mirror có policy immutable cho release artifact.

### Environment và output

- [ ] OS, architecture và container digest được ghi lại.
- [ ] Locale, timezone, charset và line ending được kiểm soát.
- [ ] Không có secret hoặc machine-specific path trong output.
- [ ] Timestamp và archive entry order deterministic.
- [ ] Plugin tạo archive/resource hỗ trợ reproducible output.
- [ ] Task custom khai báo đầy đủ input/output.

### Verification và evidence

- [ ] Build được chạy từ checkout sạch.
- [ ] Có ít nhất hai lần build độc lập.
- [ ] Artifact SHA-256 được so sánh.
- [ ] Archive contents được điều tra nếu hash khác.
- [ ] Audit manifest được lưu.
- [ ] SBOM/provenance được lưu nếu pipeline yêu cầu.
- [ ] Release chỉ được đánh dấu reproducible khi có bằng chứng rebuild.

## 27. Lỗi thường gặp và cách xử lý

### Cùng commit nhưng artifact hash khác

**Nguyên nhân:** JDK, dependency, plugin, OS, archive timestamp hoặc generated metadata khác.

**Cách xử lý:** so sánh audit manifest trước; sau đó kiểm tra archive entry, manifest, class file và diffoscope.

### java --version giống nhau nhưng bytecode khác

**Nguyên nhân:** compiler toolchain khác, JDK patch/build khác, annotation processor khác hoặc compiler flags khác.

**Cách xử lý:** kiểm tra javac --version, Gradle javaToolchains, Maven Toolchains và compiler configuration. Pin JDK image/package cụ thể.

### Dependency version giống nhau nhưng JAR bytes khác

**Nguyên nhân:** repository redeploy artifact cùng coordinates hoặc snapshot/changing module thay đổi nội dung.

**Cách xử lý:** kiểm tra checksum/signature, repository origin và immutable release policy; bật dependency verification.

### Gradle lockfile không ngăn dependency thay đổi

**Nguyên nhân:** changing dependency như SNAPSHOT có thể đổi bytes dù version coordinate giữ nguyên.

**Cách xử lý:** dùng release artifact bất biến; kiểm tra checksum/signature; không dùng lockfile thay cho content verification.

### Maven build tạo JAR có timestamp khác

**Nguyên nhân:** plugin đóng gói chưa hỗ trợ reproducible output hoặc project.build.outputTimestamp chưa được áp dụng.

**Cách xử lý:** chạy artifact:check-buildplan; pin/nâng plugin hỗ trợ; dùng artifact:compare và diffoscope.

### Gradle JAR khác thứ tự entry

**Nguyên nhân:** Gradle cũ hoặc archive task custom không bật reproducible file order.

**Cách xử lý:** bật reproducibleFileOrder; kiểm tra task custom và plugin đóng gói. Gradle 9 mặc định đã chuẩn hóa archive task chuẩn.

### Wrapper version đúng nhưng tải distribution không đáng tin

**Nguyên nhân:** URL đã pin nhưng không có checksum hoặc checksum lấy từ cùng nguồn không đáng tin.

**Cách xử lý:** lấy SHA-256 từ trang phát hành độc lập; xác minh distribution và Wrapper JAR riêng.

### CI và local khác nhau về line ending

**Nguyên nhân:** Git checkout, .gitattributes, OS hoặc resource filtering khác nhau.

**Cách xử lý:** định nghĩa line ending trong .gitattributes; chuẩn hóa encoding và kiểm tra generated resource.

### Build manifest vô tình chứa secret

**Nguyên nhân:** dump toàn bộ environment hoặc log settings có credential.

**Cách xử lý:** chỉ xuất allowlist biến môi trường không nhạy cảm; redact repository URL chứa credential; kiểm tra artifact trước khi upload.

### Hai lần build cùng máy pass nhưng máy khác fail

**Nguyên nhân:** test chỉ repeatable trong cùng workspace/user/cache; chưa phát hiện environment leak.

**Cách xử lý:** chạy ở agent/container độc lập, workspace khác và user khác; kiểm tra absolute path, home directory, locale, timezone và repository mirror.

### Build cache trả output cũ và che giấu nondeterminism

**Nguyên nhân:** task cache input chưa đầy đủ hoặc build chưa thực sự thực thi lại.

**Cách xử lý:** chạy clean build không dùng build cache; kiểm tra input/output declaration; so sánh hai lần build độc lập.

### Attestation có nhưng chưa chứng minh reproducibility

**Nguyên nhân:** attestation ghi nhận nguồn và workflow tạo artifact, không chứng minh một bên khác tái tạo được cùng bytes.

**Cách xử lý:** thực hiện independent rebuild và so sánh SHA-256; giữ attestation như bằng chứng provenance riêng.

## 28. Tài liệu tham khảo chính thức

- [Gradle Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html) — chọn JDK cho compiler, test launcher, Javadoc và phân biệt Gradle daemon JVM với project toolchain.
- [Gradle Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html) — lưu resolved dependency versions và kiểm tra lock state.
- [Gradle Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html) — xác minh checksum, signature và metadata của dependency/plugin.
- [Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html) — pin Gradle version và xác minh Wrapper JAR/distribution.
- [Gradle Best Practices for Security](https://docs.gradle.org/current/userguide/best_practices_security.html) — checksum distribution và kiểm tra Wrapper.
- [Gradle Working with Files](https://docs.gradle.org/9.9.0/userguide/working_with_files.html) — reproducible archive, timestamp và file order.
- [Maven Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html) — project.build.outputTimestamp, plugin support, artifact:compare và diffoscope.
- [Maven Wrapper](https://maven.apache.org/tools/wrapper/) — chọn Maven distribution và xác minh wrapperSha256Sum/distributionSha256Sum.
- [Maven Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains) — chọn JDK riêng cho compiler và plugin.
- [The javac Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/specs/man/javac.html) — --release và compiler options.
- [GitHub Artifact Attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations) — ghi nhận build provenance cho binary và container image.

Toolchain audit chỉ có giá trị khi nó phản ánh đúng những gì build đã thực sự dùng. Hãy ghi lại source, JDK, Wrapper, plugin, dependency, repository và environment; xác minh những đầu vào có thể tải hoặc thay đổi; chuẩn hóa output; rồi rebuild độc lập và so sánh SHA-256. Khi hai artifact khác nhau, dùng manifest và archive diff để tìm nguyên nhân cụ thể trước khi tuyên bố build đã reproducible.

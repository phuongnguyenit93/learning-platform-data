# Pipeline CI/CD, kiểm tra artifact và phát hành có thể tái lập trong Java 27

Một ứng dụng Java có thể vượt qua unit test ở máy lập trình nhưng không khởi động được trên máy chủ vì thiếu JAR phụ thuộc, dùng sai phiên bản Java, không có runtime module cần thiết hoặc có file cấu hình khác. Ngay cả khi build thành công ở CI, việc **biên dịch lại mã nguồn trên production** có thể tạo ra artifact khác với file đã được kiểm tra và phê duyệt.

Trong chương **Đóng gói và triển khai** của **Java 27**, mục tiêu là xây dựng một đường đi rõ ràng từ **source revision → build → kiểm chứng artifact → phát hành → triển khai → giám sát/rollback**, sao cho tổ chức có thể trả lời:

1. Artifact đang chạy được tạo từ **commit và cấu hình nào**?
2. **JDK, Gradle/Maven, dependency và môi trường** nào đã tham gia build?
3. Kết quả có thể được **build lại và so sánh từng byte** không?
4. Artifact triển khai có **đúng là file đã được kiểm thử** không?
5. Ai hoặc hệ thống nào có quyền **chấp thuận và thực hiện deploy**?
6. Nếu phát hiện lỗi, có thể **truy xuất, quay lại bản trước và giải thích** được không?

Bài sử dụng những API Java SE 27 và tính năng Gradle/Maven hiện hành; không dựa trên công cụ Java đã lỗi thời hoặc các tính năng preview. Các lệnh và cấu hình là **ví dụ để áp dụng trong dự án phù hợp**, không phải lệnh được tự ý thực thi lên production.

## 1. Tái lập build, kiểm tra artifact và promotion là ba bài toán khác nhau

| Khái niệm | Câu hỏi cần trả lời | Kết quả mong muốn |
| --- | --- | --- |
| **Repeatable build** | Chạy lại cùng lệnh trên một máy có ra kết quả ổn định không? | Ít sai khác giữa các lần build |
| **Reproducible build** | Với cùng source, build instructions và môi trường đã xác định, một bên độc lập có thể tạo **artifact trùng từng byte** không? | Byte-for-byte equivalence |
| **Artifact verification** | File có đúng cấu trúc, hành vi và digest/signature mong đợi không? | Artifact được kiểm tra và được tin cậy theo policy |
| **Promotion** | Có triển khai đúng **artifact đã qua các cổng kiểm chứng** không? | Một artifact bất biến đi qua staging → production |
| **Deployment** | Artifact chạy được, cấu hình đúng và dịch vụ khỏe mạnh không? | Phát hành vận hành ổn định |
| **Rollback/recovery** | Có thể phục hồi khi bản mới lỗi không? | Khôi phục phiên bản và trạng thái thích hợp |

**Không đánh đồng:**

- Hai file có cùng **SHA-256** là bằng chứng mạnh rằng nội dung file giống nhau, **không chứng minh người tạo ra file đáng tin**.
- Một file có **chữ ký số hợp lệ** có thể chứng minh tính toàn vẹn và người ký theo chính sách tin cậy, nhưng **không chứng minh mã nguồn an toàn hay không có lỗi**.
- Một build **reproducible** vẫn có thể chứa dependency có lỗ hổng.
- Một artifact đã qua test **không chắc chạy tốt trên production** nếu cấu hình, secret, schema hoặc tài nguyên khác.
- Việc chạy lại `gradle build` sau khi staging đã qua kiểm thử là **rebuild**, không phải **promote đúng artifact**.

### 1.1. Sơ đồ pipeline đề xuất

~~~~text
      Pull request / merge vào nhánh được bảo vệ
                         |
                         v
              Xác minh nguồn và quyền
                         |
                         v
          Toolchain JDK 27 + build tool đã khóa
                         |
                         v
           Resolve dependencies được kiểm soát
                         |
                         v
           Compile  →  Unit/Integration tests
                         |
                         v
           Package (JAR/runtime image/container)
                         |
                         v
           Verify structure, runtime, digest
                         |
                         v
           SBOM + provenance + ký artifact
                         |
                         v
              Publish immutable artifact
                         |
                         v
             Staging / smoke / acceptance
                         |
                         v
           Approval hoặc deployment policy
                         |
                         v
            Production: deploy by digest
                         |
                         v
           Metrics, alerts, canary, rollback
~~~~

Sơ đồ minh họa các **giai đoạn logic**. Một tổ chức có thể dùng Jenkins, GitHub Actions, GitLab CI, Azure DevOps hoặc hệ thống nội bộ; tên job và công cụ triển khai sẽ khác nhau. Yêu cầu cốt lõi là **hợp đồng, bằng chứng và quyền đi qua mỗi cổng**.

## 2. Xác định đơn vị phát hành của ứng dụng Java 27

Trước khi thiết kế CI/CD, hãy quyết định **artifact cuối cùng** là gì:

| Dạng | Bao gồm | Phù hợp khi | Những gì còn phải kiểm tra |
| --- | --- | --- | --- |
| **Thin JAR** | Class/resource của ứng dụng, thường không gói mọi dependency | Runtime/classpath được quản lý riêng | Đầy đủ classpath/module path khi chạy |
| **Executable JAR** | JAR có `Main-Class` trong manifest | Chạy bằng `java -jar` | Runtime dependencies có được phân phối đúng không |
| **Fat/uber JAR** | Gộp application classes và nhiều dependencies | Hệ đóng gói thích hợp với classpath | Trùng resource, `META-INF/services`, chữ ký cũ, license |
| **Modular JAR** | Có `module-info.class` | Ứng dụng dùng JPMS | Module dependencies và module graph |
| **Custom runtime image** | Runtime JDK tối giản do `jlink` tạo | Muốn kiểm soát modules/runtime | Platform, native libraries, dịch vụ phản chiếu động |
| **Native installer/app image** | App và runtime/launcher từ `jpackage` | Phân phối desktop hoặc hệ cài đặt | OS/architecture và signing/notarization |
| **OCI container image** | App, runtime và cấu hình filesystem/container | Dịch vụ server/container | Base image digest, user, secrets, health và resource limits |

**JAR không đồng nghĩa executable standalone.** `jar` từ JDK tạo được archive, nhưng muốn `java -jar` phải có entry point; muốn chạy các dependency bên ngoài cần đóng gói hoặc phân phối chúng theo hợp đồng đã chọn.

### 2.1. Một phát hành có thể có nhiều artifact

Ví dụ release `1.4.2` có:

~~~~text
my-service-1.4.2.jar
my-service-1.4.2.pom
my-service-1.4.2-sources.jar
my-service-1.4.2-sbom.json
my-service-1.4.2.intoto.jsonl
sha256sums.txt
container image: registry.example.test/team/my-service@sha256:...
~~~~

Đây là **tên và địa chỉ minh họa**, không phải artifact có sẵn. Mỗi file có **digest riêng**; một bản OCI image không có cùng digest với JAR nằm bên trong. Cần xác định **đơn vị được ký và triển khai**: JAR, runtime image, container image hay toàn bộ tập release.

### 2.2. Artifact không nên chứa secret môi trường

Không đặt password production, token hoặc private key vào JAR, `application.properties` được gói, OCI layer hoặc metadata provenance. Cấu hình cần chia:

- **Cố định lúc build:** tên/phiên bản module, bytecode target, dependency graph, feature được build.
- **Cấp lúc deploy:** endpoint, tài khoản dịch vụ, vùng triển khai, cấu hình tài nguyên, secret được quản lý riêng.

Nếu mỗi môi trường cần build lại JAR chỉ để đổi endpoint, cùng một commit có thể tạo nhiều artifact không tương đương và gây khó cho promotion/rollback. Ưu tiên **một binary qua các môi trường** và gắn cấu hình bên ngoài theo chính sách.

## 3. Chọn và cố định các đầu vào của build

Một build có thể xem như một hàm:

~~~~text
artifact = build(
    source revision,
    build instructions,
    JDK distribution and version,
    Gradle/Maven and plugins,
    direct + transitive dependencies,
    environment / OS / architecture,
    explicitly allowed build parameters
)
~~~~

Một bản build chỉ có thể lặp lại khi những giá trị ảnh hưởng đến output đều **được mô tả và kiểm soát**.

### 3.1. Source revision bất biến

- Mỗi release phải gắn với **commit SHA** hoặc một định danh content-addressed đáng tin.
- Một **branch name** như `main` thay đổi theo thời gian; branch không đủ để tái lập byte-for-byte.
- Tag có thể có chính sách bảo vệ, nhưng nhiều hệ thống cho phép **di chuyển tag** nếu quyền không bị khóa.
- Source tree phải sạch hoặc mọi file được sinh ra/nhập vào từ bên ngoài phải được ghi nhận rõ.

Ví dụ các lệnh **chỉ để kiểm tra** trên Git:

~~~~text
git rev-parse HEAD
git status --porcelain
git show -s --format='%H %cI' HEAD
~~~~

Không đưa biến `BUILD_TIME=now()` vào manifest hoặc resource của application nếu muốn hai lần build tạo cùng bytes. Nếu cần ghi timestamp, dùng thời điểm **được chuẩn hóa và nằm trong input**; release metadata được ghi **bên ngoài** artifact cũng là một lựa chọn.

### 3.2. JDK và compiler release Java 27

Đối với sản phẩm chạy Java 27:

~~~~text
Toolchain JDK: Java 27
Compiler target: --release 27
Expected class file major: 71
Runtime smoke test: Java 27
~~~~

`--release 27` giới hạn mức cú pháp, class-file format và JDK APIs theo Java 27. **Nó không chọn JDK compiler**; compiler thực tế phải hỗ trợ release 27.

Ví dụ Gradle Kotlin DSL (Gradle **9.8 trở lên** có hỗ trợ Java 27 theo compatibility matrix):

~~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(27)
    options.encoding = "UTF-8"
}
~~~~

Với Maven 3 có Compiler Plugin được quản lý version và đã chọn compiler JDK 27:

~~~~xml
<properties>
    <maven.compiler.release>27</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~~

**Phải kiểm tra:** JVM chạy Gradle/Maven có thể khác compiler JDK được toolchain chọn; test JVM và production JVM cũng cần xác minh riêng. JDK major 27 chưa đủ để khóa **vendor, patch release, architecture** cho build reproducibility ở mức nghiêm ngặt.

### 3.3. Khóa công cụ build và plugin

- **Gradle:** dùng Gradle Wrapper đã được review, quản lý distribution và plugin versions; kiểm tra checksum của distribution theo chính sách.
- **Maven:** dùng Maven Wrapper hoặc Maven distribution được CI quản lý; khai báo phiên bản các plugin trọng yếu, ví dụ compiler, resources, jar, surefire/failsafe và publishing.
- Các script chạy ngoài Gradle/Maven (Node, protobuf compiler, shell, code generators) cũng phải có version và input được quản lý.

**Không trộn** một bản Gradle hoặc Maven khác nhau vào cùng release candidate khi không có lý do rõ. Plugin nâng version có thể thay đổi manifest, tài nguyên, dependency resolution hoặc cấu trúc archive.

### 3.4. Khóa dependency, không sử dụng bản tự thay đổi

Một version selector động như `1.+` hoặc phụ thuộc `SNAPSHOT` có thể lấy nội dung khác vào thời điểm khác. Cần có cơ chế kiểm soát **cả phụ thuộc trực tiếp và bắc cầu**:

- **Gradle:** dependency locking và dependency verification.
- **Maven:** quản lý versions qua POM/`dependencyManagement`, BOM được khóa version, Enforcer hoặc quy trình phê duyệt dependency phù hợp.
- Không chỉ khóa **tọa độ (group/artifact/version)**: nếu repository cho phép thay đổi bytes dưới cùng tọa độ, cần thêm kiểm tra **checksum/signature**.

Một `gradle.lockfile` giúp cố định versions, nhưng **không bảo đảm tính xác thực nội dung artifact**; một `verification-metadata.xml` kiểm tra checksum/signature, nhưng **không tự chọn thay bạn một dependency version an toàn**.

## 4. Làm archive JAR/ZIP/TAR có thứ tự và timestamp ổn định

Các nguồn không xác định thường gặp khi tạo archive:

| Nguồn thay đổi | Biểu hiện | Biện pháp |
| --- | --- | --- |
| Thứ tự đọc filesystem | Các entry JAR/ZIP đảo vị trí | Thứ tự archive ổn định |
| File modification time | Timestamp mỗi entry khác nhau | Fixed/reproducible timestamp |
| Permission từ filesystem | Mode khác giữa Linux/Windows | Permission được chuẩn hóa |
| Timestamps trong manifest | Build time thay đổi | Bỏ hoặc lấy từ một input cố định |
| Random UUID / build ID | File sinh tự thay đổi | Di chuyển metadata ra ngoài hoặc dùng input có thể kiểm chứng |
| Đường dẫn tuyệt đối | Build directory/user bị nhúng vào output | Path-relative hoặc prefix chuẩn hóa |
| Locale, timezone và charset | Sinh text, sort hoặc resource khác | Cấu hình tường minh |
| Dependency hoặc plugin thay đổi | Class/resource khác | Version pin/lock + verification |
| Compression implementation | ZIP bytes khác dù nội dung giống | Khóa công cụ, version và compression settings |

### 4.1. Gradle 9+: archive reproducible mặc định

Từ **Gradle 9.0**, `AbstractArchiveTask` như `Jar`, `Zip`, `Tar` sử dụng giá trị mặc định reproducible: **file order xác định, timestamp cố định và permission chuẩn hóa**.

Nếu muốn nêu chính sách trong `build.gradle.kts` để người đọc không phụ thuộc vào kiến thức về default:

~~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isReproducibleFileOrder = true
    isPreserveFileTimestamps = false
}
~~~~

Hai thuộc tính trên là **đúng hướng** để có archive ổn định. Trên Gradle 9+ chúng cũng phù hợp với default hiện tại. Không đảo thành `isReproducibleFileOrder = false` hoặc `isPreserveFileTimestamps = true` chỉ vì một ví dụ cũ.

**Cần lưu ý:**

- Cấu hình này áp dụng với những task kế thừa `AbstractArchiveTask`; plugin đóng gói riêng có thể có cơ chế khác.
- Fixed timestamps/ordering **không giải quyết** resource generator nhúng timestamp, dependency không ổn định hay bản compiler khác.
- Gradle 9+ còn có cơ chế chuẩn hóa permission. Script cần bit executable phải được cấu hình có chủ đích; đừng mặc định mọi file xuất ra vẫn giữ permission như filesystem nguồn.

Nguồn: [Gradle — Working with Files / Reproducible Archives](https://docs.gradle.org/current/userguide/working_with_files.html).

### 4.2. Maven: `project.build.outputTimestamp`

Theo hướng dẫn Maven Reproducible Builds, một POM có thể dùng:

~~~~xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~~

Đây là một **thời điểm ổn định minh họa**, không nhất thiết là ngày phát hành. Maven Archiver và các plugin hỗ trợ sẽ dùng nó để chuẩn hóa timestamp trong archive entries. Cần nâng **plugins có hỗ trợ reproducible output**; một thuộc tính trong POM không tự sửa tất cả plugin tạo output khác.

Maven documentation ghi nhận **Maven 3.10.0** và **Maven 4.0.0-beta-5** trở đi có cơ chế bật reproducible build mode mặc định, nhưng vẫn khuyến nghị kiểm tra khả năng plugin và xác minh output thực tế. Với Maven 3 cũ hơn vẫn có thể bật thông qua property và plugin versions phù hợp.

Không nên đặt timestamp bằng **thời điểm hiện tại** mỗi lần build:

~~~~xml
<!-- PHẢN VÍ DỤ khi giá trị này đổi ở mỗi lần rebuild -->
<!-- <project.build.outputTimestamp>BUILD_TIME_NOW</project.build.outputTimestamp> -->
~~~~

Nếu muốn liên kết với một mốc source, có thể dùng **commit timestamp được chuẩn hóa** theo policy, nhưng cách đưa nó vào Maven/CI phải bảo đảm hai lần rebuild nhận đúng **cùng input**. Đừng nhầm thời điểm tạo release candidate với ngày/giờ worker đang chạy build.

Nguồn: [Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html).

### 4.3. `jar --date` của JDK 27

Nếu ứng dụng tạo JAR trực tiếp bằng tool `jar`, Java SE 27 có tùy chọn `--date` cho việc ghi **timestamp entries** ở chế độ create/update.

Ví dụ giả định thư mục `build/classes` đã có class files:

~~~~text
jar --create --file app.jar --date=2026-01-01T00:00:00Z -C build/classes .
jar --list --file app.jar
jar --validate --file app.jar
~~~~

`--date` **không tự** chuẩn hóa toàn bộ input content, thứ tự files của mọi quy trình build, các generated resources hay dependency graph. Khi cần reproducibility, hãy ưu tiên build tool có chiến lược ổn định đầy đủ và **kiểm chứng bằng digest**, không chỉ tin vào một flag.

**Phân biệt hai `--release` hoàn toàn khác nhau:**

- `javac --release 27`: chọn mức Java được phép **khi biên dịch**.
- `jar --release 27`: tạo **versioned entries của multi-release JAR** trong `META-INF/versions/27`; không phải lựa chọn compiler release.

Không dùng `jar --release 27` để “bảo đảm code tương thích Java 27” khi chưa có multi-release JAR design rõ ràng.

## 5. Kiểm tra cấu trúc JAR và runtime Java 27

### 5.1. Liệt kê và kiểm tra JAR bằng JDK tool

~~~~text
jar --list --file build/libs/my-service.jar
jar --validate --file build/libs/my-service.jar
jar --describe-module --file build/libs/my-service.jar
~~~~

`jar --validate` trong Java 27 kiểm tra những lỗi như **trùng tên entry**, đường dẫn không hợp lệ hoặc API không nhất quán của một **multi-release JAR**. Nó không thực thi unit test và **không xác minh tính xác thực của publisher**.

`jar --describe-module` hữu ích khi artifact là modular JAR hoặc có automatic module name; kết quả phụ thuộc kiểu JAR và metadata thực tế. Không khẳng định chỉ cần có tệp `MANIFEST.MF` là đã trở thành JPMS module.

### 5.2. Xác minh entry point

Một JAR để chạy bằng `java -jar` cần `Main-Class` trong manifest. Ví dụ Gradle Kotlin DSL:

~~~~kotlin
plugins {
    application
}

application {
    mainClass.set("com.example.Main")
}

tasks.jar {
    manifest {
        attributes("Main-Class" to "com.example.Main")
    }
}
~~~~

`application.mainClass` cấu hình entry point cho Gradle Application plugin; `Main-Class` cho phép launcher `java -jar` tìm class chính. Với project có dependency bên ngoài, một **thin JAR** vẫn cần các dependency đó trong runtime classpath; `Main-Class` **không tự tạo fat JAR**.

Ví dụ một chương trình Java:

~~~~java
package com.example;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Java feature: " +
                Runtime.version().feature());
    }
}
~~~~

Khi phát hành chỉ nhắm Java 27, smoke test nên chạy trên **Java 27**:

~~~~text
java --version
java -jar my-service.jar
~~~~

Kỳ vọng ví dụ in giá trị `27` khi JVM thực thi là Java 27. Tùy policy, app được build `--release 27` có thể chạy trên JVM mới hơn có tính tương thích thích hợp, nhưng cần kiểm thử runtime ấy chứ không chỉ dựa trên version number.

### 5.3. Kiểm tra class-file version

~~~~text
javap -verbose -classpath build/libs/my-service.jar com.example.Main
~~~~

Với bytecode bình thường được biên dịch theo **`--release 27`**, class-file major version là **71**. Nếu artifact gồm class từ nhiều nguồn, cần kiểm tra **những class liên quan trong cả runtime dependency graph**, không chỉ một class của ứng dụng.

`UnsupportedClassVersionError` có thể xuất hiện khi deploy một JAR/class Java 27 vào JVM cũ hơn. Thấy compiler JDK 27 trong CI cũng không bảo đảm container base image đang chạy Java 27.

### 5.4. Kiểm tra signatures nếu chính JAR được ký

~~~~text
jarsigner -verify -verbose -certs -strict my-service-signed.jar
~~~~

`jarsigner` là công cụ JDK 27 để **ký và xác minh signed JAR**. `-strict` khiến các cảnh báo nghiêm trọng được xử lý nghiêm hơn. Chỉ kiểm tra được một chữ ký tồn tại/chính xác về mặt toán học **chưa đủ**: tổ chức còn phải xác minh certificate chain, trust anchor, revocation/timestamp và danh tính publisher theo chính sách.

**Không tự ký một JAR bằng private key đặt trong repository.** Private key cần được giữ trong kho secret/KMS/HSM hoặc cơ chế signing đáng tin với quyền truy cập hẹp và audit được.

Nếu đang kiểm tra **OCI image**, dùng công cụ ký/xác minh cho OCI artifact, không dùng `jarsigner` để suy ra trạng thái chữ ký của toàn bộ image.

### 5.5. Kiểm tra file không chứa nội dung nhạy cảm

Trước publish, xác minh archive không chứa:

- Private key, `.env` production, token hoặc mật khẩu.
- File test data có dữ liệu người dùng thật.
- Debug dump, heap dump, core dump hoặc log.
- Build caches không liên quan.
- File cấu hình CI mang secret.

`jar --list` cho phép kiểm tra tên entry, nhưng **không chứng minh nội dung file an toàn**. Cần có secret scanning/kiểm tra policy, đúng nguồn dữ liệu và quyền publish.

## 6. Java 27: `jlink` và `jpackage` trong pipeline

### 6.1. Custom runtime image bằng `jlink`

`jlink` ghép các JPMS modules và phụ thuộc module để tạo **runtime image riêng** cho ứng dụng. Ví dụ khi có module `com.example.app` trong thư mục `mods`:

~~~~text
jlink --module-path mods --add-modules com.example.app \
      --output build/runtime-image \
      --no-header-files --no-man-pages
~~~~

Các dấu `\` cuối dòng trong ví dụ biểu thị **tiếp dòng trong shell POSIX**. Trên Windows PowerShell, hãy dùng lệnh một dòng hoặc cách tiếp dòng phù hợp của PowerShell.

Sau khi tạo:

~~~~text
build/runtime-image/bin/java --list-modules
~~~~

**Các giới hạn cần chú ý:**

- Image phụ thuộc **JDK, OS và architecture** dùng liên kết; không tự coi một image Linux là artifact portable sang Windows.
- `jlink` không “đóng gói mọi classpath JAR” theo bất kỳ cách nào; cần module graph phù hợp.
- Ứng dụng dùng reflection, `ServiceLoader`, JNI hoặc dynamic loading cần test đủ module/provider thực tế.
- Nhiệm vụ cập nhật runtime image theo **bản vá bảo mật JDK** thuộc trách nhiệm người xây dựng/phát hành, không phải tự động theo sau mỗi lần phát hành JDK.

### 6.2. `jpackage`: app image và installer

`jpackage` tạo app image hoặc native package phù hợp hệ điều hành. Ví dụ ứng dụng classpath có `app.jar` trong `dist/input`:

~~~~text
jpackage --type app-image --name MyApp \
    --input dist/input \
    --main-jar app.jar \
    --main-class com.example.Main \
    --dest dist/output
~~~~

Ví dụ dùng shell POSIX; trên hệ khác cần đổi syntax path/continuation. `jpackage` có thể tự dùng `jlink` để tạo runtime nếu không truyền `--runtime-image`. Muốn kiểm soát runtime image do quy trình riêng xây dựng, cung cấp `--runtime-image` theo tài liệu JDK 27.

**Không tuyên bố native installer reproducible từng byte trên mọi OS** khi chưa kiểm chứng: metadata của installer, chữ ký số, notarization, compression, filesystem/OS tools và timestamps có thể thay đổi. Với `jlink`/`jpackage`, hãy coi **JDK vendor/patch, OS image, tooling và cấu hình signing** là input quan trọng.

Nguồn: [Oracle Java SE 27 — jlink](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jlink.html), [jpackage](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jpackage.html).

## 7. Kiểm soát dependency và chuỗi cung ứng

Một build có mã nguồn không đổi vẫn có thể tạo JAR khác nếu dependency resolution bị thay đổi. Tải những artifact không được kiểm chứng còn có thể khiến mã không đáng tin được chạy **ngay trong quá trình build**, đặc biệt nếu đó là plugin hoặc annotation processor.

### 7.1. Gradle dependency locking

Gradle cho phép khóa version cho các configuration được resolve. Ví dụ `build.gradle.kts`:

~~~~kotlin
plugins {
    java
}

dependencyLocking {
    lockAllConfigurations()
}
~~~~

Sinh lock state **trong quy trình được review**, ví dụ khi đã quyết định nâng dependency:

~~~~text
./gradlew dependencies --write-locks
~~~~

Kiểm tra và commit các `gradle.lockfile` được tạo theo từng project/subproject; những configuration chưa được resolve trong lượt chạy ấy có thể không có lock state tương ứng. Với build đa module và cấu hình động, phải bảo đảm các configuration được sử dụng thực tế đều được xét.

**Không tự sinh lại lock files trong bước CI release để vượt lỗi resolution**, vì làm vậy có thể âm thầm nâng dependency. Cập nhật lock file là thay đổi source/build definition cần review.

`SNAPSHOT` hoặc **changing modules** có thể thay đổi nội dung trong cùng một version. Version locking không làm chúng trở nên immutable; đối với phát hành ổn định, ưu tiên version phát hành cố định và artifact repository có policy không ghi đè.

Nguồn: [Gradle — Locking Versions](https://docs.gradle.org/current/userguide/dependency_locking.html).

### 7.2. Gradle dependency verification

Gradle có **dependency verification** để kiểm tra checksums và, khi được cấu hình, signatures của artifact tải về. Cấu hình thường nằm tại:

~~~~text
gradle/verification-metadata.xml
~~~~

Một cách **khởi tạo metadata để review**:

~~~~text
./gradlew --write-verification-metadata sha256,pgp help
~~~~

Sau lệnh khởi tạo, người bảo trì phải xem toàn bộ thay đổi, xác nhận hash/key từ nguồn tin cậy và commit metadata đã phê duyệt. **Đừng tự động chấp nhận mọi checksum vừa tải cùng một nguồn không đáng tin**: bản thân việc tạo file hash không xác thực nhà phát hành.

Những lần CI bình thường nên **xác minh** metadata đã khóa, không **tự tạo lại** metadata khi kiểm tra thất bại. Cấu hình Gradle có thể kiểm tra cả artifact và metadata như POM.

**Hai lớp kiểm soát khác nhau:**

| Cơ chế | Ngăn được | Không tự ngăn được |
| --- | --- | --- |
| Lockfile | Version bắc cầu thay đổi ngoài dự kiến | Bytes của cùng version bị thay đổi |
| Checksum verification | Artifact không khớp fingerprint được tin cậy | Artifact gốc vốn đã độc hại |
| Signature verification | Artifact không khớp người ký/khóa được tin cậy | Kẻ ký được tin vẫn phát hành lỗ hổng |
| Vulnerability scanning | Một số lỗ hổng đã được ghi nhận | Lỗ hổng chưa được biết hoặc logic nghiệp vụ sai |

Nguồn: [Gradle — Securing Dependencies](https://docs.gradle.org/current/userguide/dependency_verification.html).

### 7.3. Maven dependency và plugin management

Với Maven, nên kiểm soát:

- `<dependencyManagement>` hoặc BOM **có version tường minh**.
- Các dependency trực tiếp với tọa độ version cụ thể; tránh floating ranges khi release.
- `<pluginManagement>` / `<plugins>` có version cố định cho plugin quan trọng.
- Plugin repository và artifact repository từ nguồn đáng tin.
- Chính sách snapshot/retention và cấm ghi đè release artifact.
- Nếu cần pin cả dependency graph hiệu lực, dùng quy trình/plugin được quản trị và lưu dấu vết của resolved graph; **Maven không có lockfile chuẩn tương đương Gradle cho mọi POM theo mặc định**.

Ví dụ POM rút gọn:

~~~~xml
<properties>
    <maven.compiler.release>27</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.16.0</version>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.5.0</version>
        </plugin>
    </plugins>
</build>
~~~~

Đây là **các phần tử bên trong một POM**, không phải một XML document hoàn chỉnh. Version plugin trong bài là **ví dụ version được phát hành**; dự án nên kiểm tra version ổn định được phê duyệt và khả năng tương thích với Maven/JDK 27 trước khi dùng thật.

Không dùng lệnh cập nhật toàn bộ dependency hoặc plugin versions ngay trong pipeline release mà không review. Việc update version nên là một PR thay đổi build inputs và được chạy thử trên CI trước khi merge.

### 7.4. SBOM không phải khóa phiên bản

Một **Software Bill of Materials (SBOM)** ghi nhận thành phần của sản phẩm, thường theo những chuẩn như **CycloneDX** hoặc **SPDX**. SBOM giúp tìm phạm vi ảnh hưởng khi một dependency có vấn đề, nhưng không tự:

- Chặn dependency nguy hiểm được tải.
- Xác minh chữ ký publisher.
- Làm cho JAR reproducible.
- Thay thế vulnerability scanning.

SBOM phải gắn với **artifact cụ thể**, ideally bằng digest và nguồn dữ liệu từ **resolved dependencies** chứ không chỉ một danh sách dependency khai báo. Khi dùng plugin tạo SBOM, phải khóa phiên bản plugin, kiểm tra output và ký/attest phù hợp theo chính sách phát hành.

## 8. Kiểm chứng tính tái lập bằng hai build thực sự độc lập

Reproducible build không được chứng minh chỉ bằng câu “đã bật reproducible flags”. Cần **thử tái lập** rồi so sánh output.

### 8.1. Kiểm tra sơ bộ tại một môi trường

Một thử nghiệm đơn giản cho Gradle trên Linux/macOS:

~~~~text
# Hai lần build trên cùng một revision, ví dụ có lệnh build phù hợp.
./gradlew clean jar
sha256sum build/libs/my-service.jar

./gradlew clean jar
sha256sum build/libs/my-service.jar
~~~~

Nếu SHA-256 khác, artifact **không giống nhau từng byte**. Kiểm tra tên file thật trong `build/libs`, vì mặc định Java plugin đặt tên JAR theo project/version, không nhất thiết đúng `my-service.jar`.

Nếu SHA-256 giống nhau, đây mới là **kiểm tra repeatability sơ bộ trên cùng môi trường**. Cache, môi trường, plugin hoặc trạng thái workspace vẫn có thể che một số nguồn sai khác. Không coi nó là bằng chứng bên độc lập có thể tái lập artifact.

Với PowerShell trên Windows:

~~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath "build\libs\my-service.jar"
~~~~

Không dùng CRC32, MD5 hoặc SHA-1 làm fingerprint bảo mật chính của release; chúng có những giới hạn về khả năng chống collision.

### 8.2. Kiểm tra hai workspace sạch

Một kiểm thử mạnh hơn:

~~~~text
Workspace A: checkout commit S, JDK 27 build image E, dependencies D
    → clean build → artifact A → SHA-256 H1

Workspace B: checkout commit S độc lập, build image E, dependencies D
    → clean build → artifact B → SHA-256 H2

Điều kiện PASS: H1 == H2 và artifact được kiểm chứng đúng loại.
~~~~

Nếu dùng cùng build image/container, bài test xác minh **tính tái lập trong một môi trường đã khóa**. Nếu muốn chứng minh một bên thứ ba có thể tự tái lập, cần chạy trong một **môi trường độc lập** và so sánh kết quả, không chỉ clone cùng workspace với cache chung.

**Điều kiện đầu vào:**

1. Cùng exact source commit và files sinh ra được quản lý.
2. Cùng JDK vendor/patch, Gradle/Maven, build plugin và dependency content.
3. Cùng giá trị timestamp chuẩn hóa.
4. Không phụ thuộc vào current time, đường dẫn máy, random seed hay build host ID.
5. Không thay đổi artifact **sau** bước kiểm chứng mà không tạo một digest/attestation mới.

### 8.3. Maven Artifact Plugin so sánh build

Maven hướng dẫn một phép kiểm tra thực tế:

~~~~text
# Build và cài artifact tham chiếu vào local repository:
mvn clean install

# Build lại từ cùng source rồi so sánh với tham chiếu:
mvn clean verify artifact:compare
~~~~

`artifact:compare` thuộc Maven Artifact Plugin; tùy version/plugin prefix resolution mà môi trường cần khai báo plugin hoặc gọi goal bằng tên đầy đủ. Ví dụ tường minh:

~~~~text
mvn clean verify org.apache.maven.plugins:maven-artifact-plugin:3.7.0:compare
~~~~

**Cần phân biệt:** kiểm tra sau khi `install` vào local repository **không phải độc lập về hạ tầng**. Kết quả so sánh cùng máy dễ bỏ sót những input từ hostname, locale, path hoặc state của machine. Muốn đánh giá sâu, dùng một workspace/agent tách biệt với cùng source và định nghĩa toolchain rõ ràng.

Nguồn: [Maven — Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html), [Maven Artifact Plugin — compare](https://maven.apache.org/plugins/maven-artifact-plugin/compare-mojo.html).

### 8.4. Khi hash khác nhau, kiểm tra gì?

Theo thứ tự:

1. Xác minh đang so **cùng loại artifact, cùng source commit**.
2. Giải nén/so sánh danh sách **entry names, order, timestamps và permissions**.
3. So sánh `MANIFEST.MF` và metadata được sinh.
4. So sánh class files/resources để phân biệt lỗi compiler và lỗi archiver.
5. Tìm hostname, username, workspace absolute path, timezone, build time và random UUID được nhúng vào file.
6. Xem dependency lock/verification và classpath thứ tự có ổn định không.
7. Đối chiếu JDK vendor/patch, build plugins, locale và compression implementation.

Khi cần so sánh hai archive, nên dùng một công cụ **diffoscope** hoặc công cụ phân tích archive đã được tổ chức phê duyệt. Một checksum khác chỉ báo **có sự khác biệt**, nó không giải thích nguyên nhân.

### 8.5. Chữ ký và metadata phát hành có thể làm bytes thay đổi

Đừng ký một artifact rồi kỳ vọng nó luôn có cùng bytes với **artifact unsigned**. Các bước như `jarsigner`, timestamp server, notarization, attestation hoặc tạo image manifest có thể sinh metadata mới.

Chính sách rõ ràng:

- Kiểm chứng reproducibility trên **unsigned/build output** nếu đó là đơn vị được build lại.
- Ghi hash của **artifact cuối cùng sau signing** khi triển khai.
- Nếu muốn signed artifact cũng reproducible từng byte, phải kiểm soát thuật toán ký, timestamp và toàn bộ dữ liệu chữ ký; không mặc nhiên điều đó xảy ra.
- Provenance phải nói rõ **digest của object nào** là subject, không dùng hash của bản unsigned để xác minh nhầm bản đã ký.

## 9. Kiểm tra chuỗi cung ứng: SBOM, chữ ký và provenance

Trong phát hành Java hiện đại, câu hỏi không chỉ là “build được chưa?” mà còn là “**artifact này xuất phát từ đâu và có được sửa sau bước CI không?**”.

### 9.1. Digest, signature và attestation khác nhau

| Bằng chứng | Mô tả | Điều chưa được bảo đảm |
| --- | --- | --- |
| **SHA-256 digest** | Fingerprint của chính bytes artifact | Không xác thực ai tạo ra hoặc ai phê duyệt |
| **Digital signature** | Chứng minh một đối tượng được ký bởi khóa/định danh được tin theo policy | Người ký có thể ký mã lỗi hoặc mã độc |
| **SBOM** | Danh sách thành phần và phiên bản của sản phẩm | Không xác minh artifact build đúng từ source |
| **Build provenance** | Thông tin về builder, source revision, build inputs và subject digest | Chất lượng và độ tin cậy của builder còn phải được đánh giá |
| **Test report** | Bằng chứng một tập kiểm thử đã chạy và kết quả | Không chứng minh mọi hành vi và môi trường production |
| **Vulnerability report** | Đối chiếu thành phần với cơ sở dữ liệu lỗ hổng đã biết | Có thể thiếu lỗ hổng mới/chưa được công bố |

Các bằng chứng phải gắn với **đúng digest** và được lưu theo chính sách để có thể đối chiếu sau triển khai. Bản report tạo cho một JAR khác tên nhưng cùng version string **không đủ** làm bằng chứng kiểm thử artifact đang chạy.

### 9.2. Build provenance theo mô hình SLSA

SLSA dùng khái niệm **provenance** để mô tả một build đã tạo artifact như thế nào. Một attestation có thể gồm:

- **Subject:** artifact và digest SHA-256 của nó.
- **Builder:** nền tảng hoặc hệ thống CI đã thực hiện build.
- **Build definition:** source repository/commit, tham số build, dependency inputs hoặc cách xác định chúng.
- **Run details:** thông tin về invocation và môi trường theo khả năng của nền tảng.
- **Chữ ký/định danh ký:** để bên nhận xác minh attestation đến từ builder được phép, tùy cơ chế triển khai.

Trong mô hình hiện hành, một dạng predicate phổ biến là **`https://slsa.dev/provenance/v1`** trong khuôn khổ **in-toto attestation**. Không tự soạn một JSON có trường tên `provenance` rồi gọi là SLSA-compliant nếu không đúng schema và **không có cơ chế xác minh danh tính builder**.

Một đường đi:

~~~~text
Commit S ──> Trusted CI Build B ──> Artifact sha256:H
                │                       │
                └──> Signed provenance ─┘
                          |
                          v
             Release verification policy
             "Allowed repo + builder + branch + H"
                          |
                          v
                        Promote
~~~~

**Cách kiểm tra khi deploy:** so sánh digest của artifact sắp chạy với **subject digest** trong attestation, đồng thời xác thực danh tính builder, source revision/branch được phép và các điều kiện policy khác. Một chữ ký hợp lệ từ builder **không nằm trong danh sách cho phép** vẫn không đủ để deploy.

Nguồn: [SLSA — Build Provenance](https://slsa.dev/spec/v1.0/provenance).

### 9.3. SBOM theo resolved graph, không chỉ declared dependencies

Một `pom.xml` hoặc `build.gradle.kts` thường chỉ có **dependency trực tiếp**, trong khi runtime có thể kéo nhiều thư viện **transitive**. SBOM nên phản ánh những gì thật sự nằm trong **runtime artifact** và chỉ rõ nguồn dữ liệu.

Một SBOM hữu ích có thể ghi:

- Component name, version, package URL (purl) hoặc ID thích hợp.
- Source/license và quan hệ phụ thuộc theo khả năng của tool.
- Digest của component hoặc file liên quan nếu có.
- Build artifact/release version được SBOM mô tả.
- Format/schema (CycloneDX hoặc SPDX) và tool tạo.

**Cẩn trọng:** fat JAR, shaded package, dependency bị relocate và native binaries có thể làm mapping “dependency đã khai báo ↔ thành phần đang ship” phức tạp. Chạy SBOM generation ở đúng giai đoạn và kiểm tra danh sách thành phần, không mặc định một plugin đã tìm thấy toàn bộ runtime content.

### 9.4. Thời điểm tạo và lưu bằng chứng

Một thứ tự thường hợp lý:

~~~~text
Build output
   |
   +--> content/structure/runtime tests
   |
   +--> reproducibility comparison
   |
   +--> digest final unsigned artifact
   |
   +--> signing / publication packaging
   |
   +--> digest final distributable artifact
   |
   +--> SBOM + provenance/attestation bound to intended digest(s)
   |
   +--> upload artifact + metadata to immutable repository
~~~~

Thứ tự thực tế có thể khác tùy hệ thống ký/attest, nhưng **không được để report mô tả một bytestring rồi deploy một bytestring khác**. Nếu cần signing trước khi tạo attestation, hãy xác định rõ subject digest của bản signed. Nếu ký bản unsigned, cần một cách liên kết hai đối tượng có thể xác minh.

### 9.5. Điều gì xảy ra khi phát hiện lỗ hổng sau release?

Reproducible artifact không có nghĩa “không cần rebuild khi dependency lỗi”. Quy trình đúng:

1. Dùng SBOM/danh sách release tìm những artifact chứa dependency bị ảnh hưởng.
2. Xác minh tính áp dụng (reachable/exploitable context) và mức độ ưu tiên sửa.
3. Sửa dependency hoặc code theo PR/commit mới.
4. Chạy pipeline và tạo **artifact mới có digest mới**.
5. Deploy bản mới qua staging/production và theo dõi kết quả.

**Không sửa bytes của bản release cũ dưới cùng một tag/version bất biến**, vì làm mất khả năng truy xuất và so sánh.

## 10. Thiết kế các cổng (*gates*) của pipeline CI/CD

Một pipeline nên có các cổng **fail closed**: không đi sang phát hành nếu bằng chứng bắt buộc bị thiếu hoặc thất bại.

### 10.1. Ma trận giai đoạn và điều kiện đạt

| Giai đoạn | Kiểm tra | Điều kiện qua cổng |
| --- | --- | --- |
| **Source admission** | Nhánh/commit được bảo vệ, review, policy | Revision đã được phê duyệt |
| **Environment** | JDK 27, Gradle/Maven versions, toolchain | Đúng bản hỗ trợ |
| **Dependency resolution** | Lock, checksums/signatures, repository | Graph hợp lệ, không có mismatch |
| **Compile** | `javac --release 27`, generated source | Không có lỗi compiler |
| **Static quality** | Formatting, lint, analyzer theo policy | Không có vi phạm blocking |
| **Unit tests** | Domain logic | Test suite bắt buộc PASS |
| **Integration tests** | Database, HTTP, queue, TLS, config | Luồng tích hợp quan trọng PASS |
| **Package** | JAR/image/OCI | Output được tạo đầy đủ |
| **Artifact validation** | Manifest, entries, class version, runtime, secret scan | Artifact thực sự chạy đúng |
| **Security** | Vulnerability/secret/license/policy | Không có vi phạm vượt ngưỡng |
| **Reproducibility** | Rebuild so sánh digest khi bắt buộc | Digest/byte comparison PASS |
| **Attestation** | SBOM, signature, provenance | Bằng chứng hợp lệ và gắn đúng digest |
| **Publish** | Upload vào artifact registry bất biến | Có content digest và metadata |
| **Staging** | Deploy đúng digest, smoke, observability | Trạng thái sức khỏe đạt |
| **Production approval** | Quyền, thời điểm, policy/approval | Chấp thuận hợp lệ |
| **Production deployment** | Deploy đúng digest từ staging | Health/SLO đạt, có rollback plan |

Các kiểm tra bảo mật có thể có chính sách **ngăn phát hành**, **yêu cầu duyệt ngoại lệ** hoặc **cảnh báo** tùy rủi ro; cần công bố rõ ai có thẩm quyền ngoại lệ, thời hạn và bằng chứng. Không viết automation “nếu scanner lỗi thì vẫn phát hành để tránh chậm tiến độ” như quy tắc mặc định.

### 10.2. Pull request không được tự có quyền publish production

Một PR từ fork hoặc nguồn chưa tin cậy có thể sửa script build để chạy mã tùy ý. Vì vậy:

- Công việc **test PR** không nhận production deploy token, private signing key hoặc secret có quyền rộng.
- Quyền **publish/release** chỉ cấp cho workflow được bảo vệ, gắn với commit/tag và policy đã duyệt.
- Không tái sử dụng workspace/cache/outputs không tin cậy làm input trực tiếp cho job privileged mà không kiểm tra.
- Nếu nền tảng hỗ trợ short-lived identity/OIDC, ưu tiên credential ngắn hạn theo policy thay vì token cố định trong repository.
- Khóa action/plugin versions và dùng nguồn tải được phê duyệt.

Điều này quan trọng vì **build scripts là code có thể thực thi**, không chỉ dữ liệu cấu hình. Một dependency hoặc plugin độc hại có thể chạy ngay ở bước resolve/build trước khi ứng dụng được đóng gói.

### 10.3. Chỉ build một lần cho cùng release candidate

Một quy trình có thể có hai loại build:

1. **Verification builds:** CI trên PR/branch để xác minh commit đang phát triển.
2. **Release candidate build:** build từ commit đã phê duyệt, tạo artifact được lưu bất biến và gắn digest.

Sau khi release candidate đã đạt staging, **production nhận chính digest đó**. Không tạo một `release.jar` mới bằng cách chạy `./gradlew build` trong job deploy.

Nếu bắt buộc có quá trình **rebuild độc lập** để xác minh reproducibility, output của rebuild được dùng để **so sánh**, không tự trở thành artifact production khác khi chưa qua cùng cổng release.

### 10.4. CI có thể song song hóa nhưng phải giữ phụ thuộc đúng

Ví dụ:

~~~~text
                 checkout / verify commit
                           |
                           v
                    resolve dependencies
                           |
              +------------+------------+
              |            |            |
              v            v            v
          unit tests    static checks   integration tests
              |            |            |
              +------------+------------+
                           |
                      package job
                           |
                   artifact verification
                           |
                     security checks
                           |
                    publish release
                           |
                 staging -> production
~~~~

Các job song song không nên cùng **ghi đè một output directory trên shared workspace**. Mỗi job nên có working directory và artifact riêng, rồi tổng hợp bằng cách tải đúng output được gắn SHA/digest. Không cho pipeline dùng “file mới nhất trong thư mục” như cách chọn release.

## 11. Ví dụ pipeline mức logic cho Java 27

Ví dụ này không giả vờ là cấu hình chạy được trên mọi CI provider. Nó là **đặc tả độc lập nền tảng** để ánh xạ sang Jenkins/GitHub Actions/GitLab CI/nhà cung cấp khác.

~~~~yaml
# Pipeline minh họa - pseudo YAML, KHÔNG phải file provider-specific.
source:
  trigger: "protected branch or approved release tag"
  revision: "immutable commit SHA"

build:
  jdk: "27, pinned vendor/update/image digest"
  buildTool: "approved Gradle Wrapper or Maven distribution"
  dependencyPolicy: "locked and verified"
  command: "clean test package"

qualityGates:
  required:
    - source-policy
    - unit-tests
    - integration-tests
    - artifact-structure
    - runtime-smoke-java27
    - secret-and-vulnerability-policy
    - digest-recording
    - provenance-verification

publish:
  artifactRepository: "immutable registry"
  metadata: "commit, toolchain, SHA-256, SBOM, provenance"

staging:
  input: "published artifact digest"
  requiredChecks: "smoke + readiness + metrics"

production:
  input: "the exact same digest used in staging"
  requires: "approval, environment policy, rollback plan"
~~~~

Mỗi giá trị dạng text ở trên là **yêu cầu thiết kế**, không phải cú pháp CLI đã được provider thực thi. Khi chuyển thành file CI cụ thể, phải tham khảo tài liệu provider về authentication, artifact passing, job permissions và expression syntax. Không coi pseudo YAML là pipeline đã chạy thành công.

### 11.1. Ví dụ chuỗi lệnh cho Gradle trong job build

Giả định:

- CI có Java 27 theo build image được kiểm soát.
- Gradle Wrapper đã được review, version hỗ trợ Java 27.
- `build.gradle.kts` có Java toolchain 27, `options.release.set(27)`, lock/verification theo policy.
- `jar` task tạo một JAR và test riêng đã cấu hình.

~~~~text
java --version
javac --version

./gradlew --version
./gradlew -q javaToolchains

./gradlew --no-daemon clean build

# Thay bằng tên JAR thật được task jar tạo:
jar --validate --file build/libs/my-service.jar
jar --list --file build/libs/my-service.jar
sha256sum build/libs/my-service.jar
~~~~

`--no-daemon` làm giảm tái sử dụng daemon giữa các invocation của Gradle nhưng **không tự** tạo một môi trường hermetic hoặc bảo đảm reproducibility; Gradle có thể dùng một daemon tạm thời theo cấu hình JVM. Quan trọng hơn là build image, toolchain, dependency content và artifact checks.

### 11.2. Ví dụ chuỗi lệnh cho Maven

Giả định POM có cấu hình compiler release 27, Maven toolchain nếu cần, plugin versions được quản lý và timestamp ổn định:

~~~~text
mvn --version
mvn -B -V clean verify

jar --validate --file target/my-service-1.4.2.jar
jar --list --file target/my-service-1.4.2.jar
sha256sum target/my-service-1.4.2.jar
~~~~

`mvn verify` chỉ thực thi các plugin/goals đã được bind vào lifecycle. Nó **không tự sinh SBOM, provenance, scan dependency, ký JAR hoặc deploy** trừ khi POM/CI đã cấu hình những nhiệm vụ ấy.

### 11.3. Kiểm tra gói đúng với runtime, không chỉ compile

Nếu đóng gói bằng fat JAR, hãy thử chạy **chính fat JAR**, không chỉ chạy class trực tiếp từ IDE. Nếu dùng thin JAR, thử với **classpath runtime đã phân phối**. Nếu dùng `jlink` image, chạy chính `bin/java` trong image ấy. Nếu dùng OCI image, thử **OCI image digest cuối** trong môi trường staging.

Một smoke test có thể kiểm tra:

- JVM feature version là 27 theo hợp đồng.
- Ứng dụng khởi động đúng entry point.
- Configuration/secret được inject đúng nhưng không xuất hiện trong log.
- Readiness/health endpoint phản hồi phù hợp.
- Đường database/queue quan trọng kết nối được trong môi trường test.
- Shutdown và restart không làm hỏng dữ liệu.

Một lệnh `java --version` chỉ xác định JVM ở shell hiện tại; container hoặc process launcher vẫn có thể sử dụng một JVM khác. Cần xác minh **runtime thật của process chạy ứng dụng**.

## 12. Phát hành bất biến: version string, digest và release manifest

### 12.1. Version giúp con người, digest định danh bytes

Giả sử release có version `1.4.2`. Cùng tên version có thể được dùng cho nhiều định dạng:

~~~~text
my-service-1.4.2.jar                 SHA256=H1
my-service:1.4.2 (OCI tag)          digest=H2
my-service-1.4.2-linux-x64.tar.gz    SHA256=H3
~~~~

**H1, H2, H3 thường khác nhau.** Tag `1.4.2` của container image có thể bị thay đổi nếu registry không áp dụng chính sách immutable tags; digest `sha256:...` định danh content cụ thể. Với môi trường cần độ tin cậy, deploy theo **digest** và dùng version/tag làm metadata có thể tra cứu.

### 12.2. Release manifest có thể dùng làm hồ sơ phát hành

Ví dụ JSON về một release **minh họa**:

~~~~json
{
  "service": "my-service",
  "version": "1.4.2",
  "source": {
    "repository": "https://git.example.test/team/my-service",
    "commit": "FULL_COMMIT_SHA"
  },
  "build": {
    "jdkFeature": 27,
    "compilerRelease": 27,
    "buildTool": "Gradle",
    "toolVersion": "PINNED_VERSION",
    "runnerImageDigest": "sha256:RUNNER_DIGEST"
  },
  "artifacts": [
    {
      "type": "jar",
      "uri": "registry.example.test/releases/my-service-1.4.2.jar",
      "sha256": "FULL_JAR_SHA256"
    },
    {
      "type": "oci-image",
      "uri": "registry.example.test/team/my-service@sha256:IMAGE_DIGEST",
      "digest": "sha256:IMAGE_DIGEST"
    }
  ],
  "evidence": {
    "testRun": "IMMUTABLE_CI_RUN_ID",
    "sbom": "SBOM_URI_AND_DIGEST",
    "provenance": "ATTESTATION_URI_AND_DIGEST"
  }
}
~~~~

Đây **không phải một release manifest chuẩn bắt buộc của JDK**; tên trường do dự án định nghĩa. Các giá trị uppercase là placeholder, phải được thay bằng **định danh/hash thực sự** khi sinh bản ghi. Nếu cần chống sửa metadata, ký **manifest hoặc attestation** và giữ chúng trong hệ thống đáng tin.

Lưu ý: file JSON metadata có thể chứa timestamp/run ID riêng và **không nhất thiết tái lập từng byte** với JAR. Hãy phân biệt **build artifact** cần reproducible với **release record** được sinh tại thời điểm phát hành. Nếu mục tiêu là tái lập metadata, các trường ngẫu nhiên và thời gian động cũng phải được đưa vào quy trình input chuẩn hóa.

### 12.3. Không sửa release artifact đã publish

Một chính sách publication tốt:

- Artifact repository phải hỗ trợ **immutability hoặc write-once policy** cho release.
- Không cho phép overwrite một coordinate version/digest đã phát hành.
- Tách `SNAPSHOT`/nightly artifacts khỏi releases ổn định.
- Gắn release metadata, SBOM và provenance với đúng artifact digest.
- Khi có bản sửa lỗi, phát hành **version mới**; không thay bytes dưới version cũ.
- Quy định retention và khôi phục bản cũ phục vụ rollback.

Một repository có tính bất biến ở tầng artifact cũng cần quyền xóa/retention được kiểm soát. Nếu người vận hành có thể xóa mọi bản cũ, rollback vẫn có thể thất bại dù không có quyền overwrite.

## 13. OCI image và triển khai bằng digest

Trong hệ thống Java server, một OCI container image thường gồm:

- Base runtime image (JRE/JDK image hoặc custom runtime).
- JAR và resource đã được CI xây dựng.
- Metadata về entry point, working directory, user, environment.
- Các layer và manifest theo image format.

### 13.1. Khóa base image bằng digest

Ví dụ **mẫu Dockerfile minh họa**, không thể build nguyên vẹn vì digest được để placeholder:

~~~~dockerfile
# Chọn image runtime Java 27 được phê duyệt cho OS/architecture đích.
# Trong Dockerfile thật, thay FULL_BASE_DIGEST bằng digest SHA-256 hợp lệ.
FROM approved-registry.example.test/runtime/java27@sha256:FULL_BASE_DIGEST

WORKDIR /app
COPY my-service.jar /app/my-service.jar

# Base image phải cung cấp user phù hợp hoặc định nghĩa user theo policy.
USER 10001

ENTRYPOINT ["java", "-jar", "/app/my-service.jar"]
~~~~

**Lưu ý:** Đây là ví dụ cấu trúc, không phải image đã được kiểm chứng chạy được trên mọi Linux distribution. Phải xác minh base image có binary `java`, UID 10001 có thể thực thi và đọc file, chính sách filesystem/CA certs và khả năng tương thích libc/architecture khi cần.

Khóa `FROM` theo digest giải quyết rủi ro **tag bị thay đổi giữa các lần build**; nhưng **không tự** khiến image hoàn toàn reproducible. Timestamp, image builder, compression, build args, labels, metadata, multi-platform manifest và layer generation vẫn có thể tạo digest khác nhau.

### 13.2. Phân biệt digest manifest và digest layer

OCI image gồm nhiều đối tượng content-addressed. Digest của **image manifest** thường là thứ dùng để tham chiếu bản image cần deploy; với multi-platform image index, digest index khác digest manifest cho một platform cụ thể.

Vì vậy:

- Lưu **URI + digest** do registry trả về sau publish.
- Khi deploy, nền tảng phải resolve đúng platform (ví dụ linux/amd64 hoặc linux/arm64).
- Kiểm tra provenance/attestation nói rõ subject là **index hay platform manifest** theo policy.
- Không chỉ lấy checksum của JAR rồi gọi đó là digest của container image.

### 13.3. Không ghi secrets vào build args hoặc image layers

Secrets nên được cấp **lúc runtime** qua secret manager/secret store, hoặc qua cơ chế build secret chuyên dụng khi thật sự cần trong build. Tránh đưa secret vào:

~~~~text
Dockerfile ENV SECRET=...
Dockerfile ARG PASSWORD=...
RUN echo "$TOKEN" > file
Application resource chứa production password
~~~~

Ngay cả khi xóa file trong một layer sau đó, nội dung có thể còn nằm trong những layer trước. **Không** xây image có secret rồi mong xóa ở bước cuối là đủ.

### 13.4. Không nhất thiết nên dùng full JDK trên production

Với một dịch vụ đã được kiểm thử, có thể dùng:

- Runtime image Java 27 đã được quản trị và vá lỗi.
- Custom `jlink` runtime image theo module graph.
- Full JDK nếu nghiệp vụ/diagnostics có lý do rõ và được policy cho phép.

Lựa chọn runtime ảnh hưởng kích thước, module có sẵn, diagnostics, certificate store và khả năng cập nhật bảo mật. Không bỏ những module JDK mà framework cần chỉ để giảm vài MB rồi phát hành mà không chạy integration/smoke test.

## 14. Promote staging → production mà không build lại

Mục tiêu promotion:

~~~~text
CI Build
  my-service@sha256:H
             |
             v
       Artifact Registry
             |
        +----+----+
        |         |
        v         v
    Staging    Production
  digest H      digest H
~~~~

Điều gì **có thể thay đổi** giữa staging và production:

- Endpoint/hostname/database URL.
- Số instance và resource limits.
- Secret/credential.
- Feature flags theo chính sách.
- Network policies, ingress/TLS, autoscaling.

Điều gì **không nên thay đổi**:

- Bytes của JAR/container image đã được phê duyệt.
- Source revision/commit và dependency graph của artifact.
- Attestation subject digest.

### 14.1. Deployment record cần ghi gì?

| Trường | Ví dụ về ý nghĩa |
| --- | --- |
| Environment | staging / production |
| Artifact reference | URI không mutable hoặc URI + digest |
| Source revision | Commit SHA |
| Release version | Ví dụ 1.4.2 |
| Approval | Người/quy trình/policy đã phê duyệt |
| Deployment time | Thời điểm deploy, không phải embedded build timestamp |
| Config revision | Phiên bản cấu hình và feature flags liên quan |
| Migration revision | Version schema/đường nâng cấp database |
| Health outcome | Readiness, smoke tests, metrics và kết quả rollout |

Vì artifact và cấu hình môi trường là **hai đầu vào độc lập**, việc rollback có thể cần khôi phục **cả deployment config** hoặc đưa cấu hình về trạng thái tương thích. Chỉ thay JAR về bản trước có thể không đủ.

### 14.2. Lý do không rebuild khi deploy

Giả sử:

~~~~text
Staging: build commit S -> JAR hash H1 -> tests PASS
Prod:    build commit S -> JAR hash H2 -> deploy
~~~~

Nếu **H1 != H2**, kiểm thử staging không còn trực tiếp áp dụng cho bytes đang chạy ở production. Ngay cả khi hash trùng, quy trình rebuild làm tăng bề mặt rủi ro và sự phức tạp.

Phương án đúng:

~~~~text
Build commit S -> artifact digest H
                    |
             staging tests PASS
                    |
               approval
                    |
       production deploy artifact H
~~~~

Tổ chức có thể thêm bước **rebuild độc lập để kiểm chứng** với output H2, nhưng production vẫn triển khai artifact H đã được phê duyệt hoặc một artifact được xác minh theo quy trình release cụ thể.

### 14.3. Gated approval không thay bảo mật kỹ thuật

Một nút “Approve” do một người bấm không thay cho:

- Kiểm tra đúng environment và immutable digest.
- Quyền publish/deploy tách biệt.
- Chữ ký/provenance verification.
- Audit logs và lịch sử rollback.
- Chính sách release windows và segregation of duties nếu cần.

Ngược lại, một workflow tự động có đủ các policy này có thể cho phép phát hành có kiểm soát mà không cần approval thủ công cho mọi lần deploy, tùy yêu cầu tổ chức.

## 15. Rollout, health checks và rollback

### 15.1. Ba chiến lược rollout thường gặp

| Cách triển khai | Cách hoạt động | Ưu điểm | Cần kiểm soát |
| --- | --- | --- | --- |
| **Rolling update** | Thay dần từng instance/pod | Ít cần môi trường song song | Capacity, readiness, tương thích cũ/mới |
| **Blue/green** | Hai môi trường chạy song song, chuyển traffic | Có đường quay lại nhanh | DB/schema, session state, chi phí gấp đôi |
| **Canary** | Triển khai ít traffic rồi tăng dần | Quan sát rủi ro trước khi rollout toàn bộ | Routing, metrics, threshold, tự động dừng |

Không có chiến lược nào loại bỏ hoàn toàn rủi ro. Với một thao tác dữ liệu **không tương thích ngược**, rollback binary có thể không khôi phục dữ liệu đã thay đổi.

### 15.2. Health check đúng nghĩa

Nên phân biệt:

- **Liveness:** process có ở trạng thái cần được restart hay không?
- **Readiness:** instance đã sẵn sàng **nhận traffic** chưa?
- **Startup:** ứng dụng có cần thêm thời gian khởi tạo trước khi liveness xử lý?
- **Smoke test nghiệp vụ:** một số luồng hoạt động thực sự đúng (ví dụ đọc dữ liệu mẫu, ghi vào môi trường test).

Không định nghĩa một readiness endpoint luôn trả `200 OK` ngay cả khi database và dependency bắt buộc không thể truy cập, nếu việc đó làm traffic đến ứng dụng không phục vụ được. Ngược lại, **không ép liveness phụ thuộc vào mỗi lỗi thoáng qua của downstream** khiến hệ thống liên tục restart vô ích.

### 15.3. Rollback an toàn với database migration

Giả sử bản v1 dùng cột `customer_name`, còn v2 muốn đổi thành `full_name`. Một migration xóa ngay cột cũ có thể làm v1 không chạy được khi rollback.

Phương pháp thường dùng là **expand–migrate–contract**:

1. **Expand:** thêm cấu trúc mới nhưng vẫn giữ đường cũ.
2. **Migrate:** triển khai code đọc/ghi tương thích, chuyển dữ liệu dần dần.
3. **Verify:** xác nhận tính đầy đủ và sự tương thích trong giai đoạn cùng chạy v1/v2.
4. **Contract:** chỉ xóa cấu trúc cũ sau khi rollback window kết thúc và mọi consumer đã cập nhật.

**Không** tự động chạy một database migration có tính phá hủy trong bước production deploy chỉ vì artifact Java vượt qua unit tests. Migration cần quy trình backup/recovery, compatibility review và chính sách rollback rõ.

### 15.4. Khi nào nên dừng canary?

Đặt ngưỡng **trước khi deploy**:

- Error rate, HTTP 5xx, exception rate.
- Latency p95/p99 theo traffic.
- JVM heap/GC pause, thread pools, saturation.
- Database connection pool và timeout.
- Business metrics quan trọng như số đơn thành công.

Một canary có số request quá ít có thể không đủ độ tin cậy để kết luận an toàn. Nếu thiếu dữ liệu, policy nên xác định nên **giữ ở canary, tạm dừng hay rollback**, không mặc định tăng traffic.

### 15.5. Quy trình rollback có thể diễn tập

Một runbook thực tế cần:

1. Xác định bản đang chạy qua **digest**, không chỉ qua tag `latest`.
2. Xác định digest bản trước được chấp thuận và còn trong repository.
3. Kiểm tra database/config có còn tương thích với bản cũ không.
4. Chuyển deployment về digest trước hoặc chuyển traffic về blue environment theo công cụ của tổ chức.
5. Xác minh readiness, business smoke tests, metrics.
6. Ghi lại thời điểm, người/quy trình thực hiện và nguyên nhân.
7. Phân tích root cause sau sự cố, không xóa bằng chứng cần thiết.

**Không đưa vào runbook một lệnh xóa database hoặc hủy container hàng loạt không kiểm soát** chỉ để “quay về bản cũ”. Các thao tác rollback có thể ảnh hưởng dữ liệu, traffic và dịch vụ ngoài nên cần kế hoạch cụ thể.

## 16. Ví dụ Java 27: xác minh digest của file artifact

Ngoài lệnh `sha256sum` trên Linux/macOS và `Get-FileHash` trên PowerShell, Java SE 27 có `MessageDigest`, `Files` và `HexFormat` để tính SHA-256 theo luồng mà không phải tải toàn bộ JAR vào RAM.

Chương trình tự chứa dưới đây có thể lưu thành `ArtifactDigestVerifier.java`:

~~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Objects;

public final class ArtifactDigestVerifier {
    private ArtifactDigestVerifier() {
    }

    private static String sha256(Path path)
            throws IOException, NoSuchAlgorithmException {

        Objects.requireNonNull(path, "path");
        MessageDigest digest = MessageDigest.getInstance("SHA-256");

        try (InputStream input = Files.newInputStream(path)) {
            byte[] buffer = new byte[64 * 1024];
            int count;
            while ((count = input.read(buffer)) != -1) {
                if (count > 0) {
                    digest.update(buffer, 0, count);
                }
            }
        }

        return HexFormat.of().formatHex(digest.digest());
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java ArtifactDigestVerifier <file> <sha256>");
        }

        Path artifact = Path.of(args[0]);
        String expected = args[1];

        if (!expected.matches("[0-9a-fA-F]{64}")) {
            throw new IllegalArgumentException(
                    "Expected SHA-256 must contain 64 hexadecimal characters");
        }

        String actual = sha256(artifact);
        if (!actual.equalsIgnoreCase(expected)) {
            throw new IllegalStateException(
                    "Artifact digest mismatch; publication must stop");
        }

        System.out.println("Artifact digest verified: " + actual);
    }
}
~~~~

Ví dụ biên dịch và sử dụng với một file JAR **đã có**:

~~~~text
javac --release 27 ArtifactDigestVerifier.java
java ArtifactDigestVerifier path/to/my-service.jar ACTUAL_64_HEX_SHA256
~~~~

`ACTUAL_64_HEX_SHA256` là placeholder, không phải một checksum hợp lệ. Trong pipeline thật, **expected digest phải đến từ nguồn tin cậy**, ví dụ release manifest/attestation đã được ký hoặc registry với cơ chế bảo mật phù hợp. Nếu expected digest được tính từ chính file vừa tải trong cùng bước rồi so lại ngay, kiểm tra này **không xác minh được nguồn gốc file**.

Chương trình kiểm tra **bytes của file**. Nó **không** kiểm tra chữ ký, dependency vulnerability, tính hợp lệ của JAR hoặc runtime compatibility. Các cổng kiểm tra ấy vẫn cần thiết.

### 16.1. Vì sao dùng streaming?

JAR/installer/container layer có thể rất lớn. `Files.readAllBytes(path)` sẽ cần đủ bộ nhớ để tải file vào một mảng; với file lớn có thể gây áp lực heap. Dùng `Files.newInputStream` và buffer cố định giúp bộ nhớ tạm của phép tính digest **gần như không phụ thuộc kích thước artifact**.

### 16.2. Cần xử lý sai checksum theo hướng fail closed

Nếu SHA-256 không khớp:

1. Dừng bước publish/deploy đang dùng file đó.
2. Ghi nhận đường dẫn/URI, expected digest và actual digest một cách có kiểm soát.
3. Kiểm tra có nhầm platform, version, tên file hoặc cơ chế ký/post-processing không.
4. Nếu không có giải thích phù hợp, điều tra artifact repository, CI inputs và khả năng can thiệp chuỗi cung ứng.
5. Chỉ thực hiện lại quá trình kiểm chứng khi đã xác định nguồn artifact đáng tin.

**Không** “sửa” bằng cách tự cập nhật expected digest cho khớp file đang có trong cùng job deploy, vì điều đó loại bỏ ý nghĩa của kiểm tra.

## 17. Ma trận xử lý sự cố trong pipeline Java 27

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra/sửa |
| --- | --- | --- |
| CI không tìm thấy JDK 27 | Chưa cài JDK hoặc resolver/toolchain sai | Kiểm tra JDK installation, Gradle `javaToolchains`/Maven toolchains |
| Compiler báo `release version 27 not supported` | `javac` thực tế quá cũ | Chọn JDK 27 và compiler release thống nhất |
| Gradle daemon lỗi trên JDK 27 | Gradle cũ hoặc plugin không tương thích | Dùng Gradle 9.8+ phù hợp, review plugin matrix |
| Hai JAR từ cùng commit có SHA-256 khác | Timestamp, file order, random metadata, dependency/tool khác | So sánh archive entries, manifest, build inputs |
| Maven `outputTimestamp` đã đặt mà JAR vẫn khác | Plugin sinh file không deterministic hoặc không hỗ trợ | Kiểm tra plugin versions và generated sources/resources |
| Dependency checksum không khớp | Artifact thay đổi hoặc metadata sai | Dừng, xác minh nguồn và review verification metadata |
| CI “tự sửa” lockfile khi chạy | Build step có quyền cập nhật dependency resolution | Tách lock update ra PR được review |
| `jar --validate` báo lỗi | Entry trùng, đường dẫn không hợp lệ, multi-release API inconsistency | Sửa packaging task, không bỏ qua lỗi |
| `java -jar` báo `no main manifest attribute` | Manifest không có `Main-Class` | Cấu hình entry point đúng |
| `NoClassDefFoundError` sau deploy | Thin JAR thiếu runtime dependency hoặc module | Kiểm tra classpath/module path và phân phối |
| `UnsupportedClassVersionError` | Runtime JVM cũ hơn class-file target | Chạy Java 27 hoặc rebuild theo đúng hợp đồng support |
| Custom jlink image thiếu module | Module graph/reflective/service dependencies không đủ | Kiểm tra `jdeps`, service loading và integration tests |
| Container build có digest mới mỗi lần | Base tag đổi, OCI metadata/layers không ổn định | Pin base digest, builder/toolchain, so sánh manifest/layers |
| Attestation signature hợp lệ nhưng build bị từ chối | Builder/repo/source không nằm trong allowlist | Kiểm tra release policy và subject digest |
| Staging PASS nhưng production khác behavior | Config, secret, data/schema hoặc resource khác | So sánh environment contract, smoke tests và observability |
| Prod deploy nhầm artifact | Chọn theo tag mutable hoặc latest filename | Promote theo URI + digest cố định |
| Rollback binary lỗi | Schema/config mới không tương thích bản cũ | Expand–contract migrations, kiểm tra runbook |
| CI quét secret phát hiện token trong JAR | File resource/config bị đóng gói nhầm | Loại khỏi artifact, thu hồi/rotate credential bị lộ |
| Build hợp lệ nhưng thiếu SBOM | Chưa cấu hình generation/bind metadata | Tạo SBOM cho đúng resolved runtime graph |
| CI scan không chạy do provider lỗi | Job bị skip hoặc lỗi nền tảng | Cổng bắt buộc phải fail closed theo policy |

## 18. Bài tập và tiêu chí chấp nhận

### 18.1. Bài tập A — Hai lần build cùng một artifact

1. Chọn một project Java 27 có `jar` task hoặc Maven `package`.
2. Khóa commit, JDK distribution, build tool và các dependencies.
3. Bật cấu hình reproducible archives/timestamp phù hợp.
4. Build sạch trong workspace A, tính SHA-256 của JAR.
5. Build sạch độc lập trong workspace B từ **cùng commit** và cùng môi trường đã công bố.
6. So sánh SHA-256, liệt kê entry và phân tích sai khác nếu có.

**Tiêu chí đạt:** hai artifact có cùng digest; mọi input quan trọng được ghi lại. Nếu không đạt, phải nêu **nguyên nhân xác định được**, không chỉ xóa output rồi thử lại đến khi may mắn khớp.

### 18.2. Bài tập B — Phân biệt nguồn artifact

Chuẩn bị ba file trong môi trường test:

~~~~text
app-verified.jar       digest H1
app-rebuilt.jar        digest H2
app-tampered.jar       digest H3
~~~~

Chỉ file `app-verified.jar` có digest khớp release manifest đáng tin. Kiểm thử bước deploy:

- Nhận `H1` thì được phép tiếp tục sau các policy khác.
- Nhận `H2` khác `H1` thì từ chối dù cùng version string.
- Nhận `H3` thì từ chối và tạo cảnh báo.

**Tiêu chí đạt:** bước xác minh không tự cập nhật digest, không bỏ qua lỗi và không deploy theo `latest`.

### 18.3. Bài tập C — JAR chạy thật bằng Java 27

1. Biên dịch class bằng `javac --release 27` hoặc build task tương ứng.
2. Kiểm tra class-file major version `71`.
3. Kiểm tra `jar --validate` và manifest.
4. Khởi động chính artifact bằng runtime Java 27.
5. Chạy smoke test cho entry point và chức năng tối thiểu.
6. Nếu dùng thin JAR, kiểm tra classpath dependencies đi kèm.

**Tiêu chí đạt:** artifact có cấu trúc hợp lệ, chạy được trên runtime Java 27 và không thiếu dependencies.

### 18.4. Bài tập D — Rollback mà không rebuild

1. Triển khai bản A có digest `H_A` lên staging.
2. Triển khai bản B có digest `H_B`, xác minh health.
3. Mô phỏng một lỗi có kiểm soát trong staging.
4. Rollback về `H_A` bằng registry artifact đã lưu, **không chạy lại compile**.
5. Kiểm tra database/config vẫn tương thích và chạy smoke test.

**Tiêu chí đạt:** version và digest hiện chạy trở lại `H_A`, không tạo artifact mới, có audit record của quyết định rollback.

### 18.5. Tiêu chí tự đánh giá cho pipeline thực tế

| Tiêu chí | Mức cần đạt |
| --- | --- |
| Truy xuất commit | Có commit SHA chính xác cho artifact |
| Compiler/runtime | JDK 27 và `--release 27` được xác minh |
| Dependency graph | Version được khóa/ghi nhận, integrity policy có hiệu lực |
| Repeatability | Có phép thử hai build và so sánh digest |
| Security gates | Lỗi blocking không tự biến thành PASS |
| Artifact validation | Có kiểm tra cấu trúc, runnable smoke test |
| Release metadata | Có SHA-256 và bằng chứng SBOM/provenance theo policy |
| Publication | Artifact bất biến, khả năng tra cứu lịch sử |
| Promotion | Staging và production dùng **cùng digest** |
| Recovery | Có runbook rollback, đã kiểm tra schema/config compatibility |

## 19. Checklist phát hành Java 27

### Trước khi build

- [ ] Source revision/commit đã được phê duyệt; không build phát hành từ workspace sửa dở.
- [ ] CI runner hoặc build image được quản lý và có JDK 27 phù hợp.
- [ ] Gradle Wrapper/Maven distribution, plugin versions và compiler release được khóa.
- [ ] Cấu hình toolchain xác định **javac** và JVM test thực tế.
- [ ] Dependencies trực tiếp/bắc cầu được version-lock và xác minh theo policy.
- [ ] Không có secrets hay permission production trong job PR không tin cậy.

### Sau khi build và trước publish

- [ ] Unit/integration tests, static checks và security gates bắt buộc PASS.
- [ ] JAR/runtime image/container image được tạo từ nguồn và toolchain đã khai báo.
- [ ] `jar --validate`, manifest, entry point và class-file version đã kiểm tra.
- [ ] Artifact được smoke test trên Java 27.
- [ ] Có phép thử reproducibility theo mức cam kết; digest được ghi lại.
- [ ] Không có secret, dump, test fixtures nhạy cảm trong artifact.
- [ ] SBOM, provenance và chữ ký/attestation được gắn đúng subject digest.
- [ ] Artifact đã lưu vào registry có chính sách bất biến và retention.

### Trước và sau production deploy

- [ ] Production dùng **chính digest** staging đã xác minh, không rebuild.
- [ ] Source revision, approval và config revision được ghi vào deployment record.
- [ ] Secrets được cấp tại runtime, không lấy từ layer/image.
- [ ] Có readiness/liveness/startup checks phù hợp.
- [ ] Database migrations có chính sách tương thích ngược và rollback.
- [ ] Canary/rolling/blue-green có ngưỡng đánh giá, thời gian quan sát và phương án dừng.
- [ ] Đã chuẩn bị bản trước trong registry và kiểm tra quy trình rollback.
- [ ] Alerts, tracing và metrics theo dõi đủ để xác định lỗi sau phát hành.
- [ ] Có thông tin liên hệ, runbook và audit trail của quyết định release.

## 20. Tài liệu chính thức và chuẩn tham khảo

- [Oracle Java SE 27 — jar](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jar.html): `--create`, `--date`, `--validate`, `--describe-module` và multi-release JAR.
- [Oracle Java SE 27 — javac](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): compiler `--release`, class-file target và APIs nền tảng.
- [Oracle Java SE 27 — javap](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javap.html): xem class-file metadata.
- [Oracle Java SE 27 — jarsigner](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jarsigner.html): ký và xác minh signed JAR.
- [Oracle Java SE 27 — jlink](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jlink.html): tạo runtime image từ JPMS modules.
- [Oracle Java SE 27 — jpackage](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jpackage.html): app image và native installer.
- [Oracle Java SE 27 — MessageDigest](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/MessageDigest.html): SHA-256 digest API.
- [Oracle Java SE 27 — HexFormat](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/HexFormat.html): biểu diễn digest theo hexadecimal.
- [Gradle — Java Compatibility](https://docs.gradle.org/current/userguide/compatibility.html): Java 27 được hỗ trợ từ Gradle 9.8.0.
- [Gradle — Reproducible Archives](https://docs.gradle.org/current/userguide/working_with_files.html): deterministic order, timestamps, permissions.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): khóa resolved dependency versions.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): checksums và signatures.
- [Maven — Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html): `outputTimestamp` và kiểm chứng độc lập.
- [Maven Artifact Plugin — compare](https://maven.apache.org/plugins/maven-artifact-plugin/compare-mojo.html): so sánh artifact với reference build.
- [SLSA — Build Provenance](https://slsa.dev/spec/v1.0/provenance): subject, builder, build definition và attestation.
- [CycloneDX](https://cyclonedx.org/specification/overview/) và [SPDX](https://spdx.dev/use/specifications/): các định dạng SBOM phổ biến.

**Kết luận:** Pipeline CI/CD cho **Java 27** không kết thúc ở một lần chạy `gradle build` hoặc `mvn package` thành công. Cần cố định **source, toolchain, dependencies và archive metadata**, rồi **xác minh artifact thực sự** bằng cấu trúc, runtime smoke tests, digest và các bằng chứng chuỗi cung ứng. Sau khi release candidate đã đạt kiểm chứng, hãy **publish artifact bất biến và deploy đúng digest ấy qua staging đến production** thay vì rebuild mỗi lần triển khai. Reproducibility, integrity, provenance, authorization, observability và rollback là những lớp bổ trợ: chỉ khi phối hợp chúng mới có thể tạo ra một quy trình phát hành có thể truy vết, kiểm toán và phục hồi an toàn.

# Build lặp lại được với JDK và công cụ đã cố định trong Java 17

Một bản build đáng tin cậy cần cho kết quả nhất quán khi chạy lại từ cùng mã nguồn và cùng đầu vào. Nếu máy lập trình viên dùng một bản JDK, CI dùng bản khác, Gradle hoặc Maven tự tải phiên bản mới, dependency được khai báo bằng version động hoặc archive chứa timestamp thay đổi theo mỗi lần build, hai lần build có thể tạo ra kết quả khác nhau dù code không đổi.

**Build lặp lại được (reproducible build)** là quá trình tạo artifact có thể tái tạo từ cùng đầu vào đã được xác định. Mục tiêu mạnh nhất là hai lần build độc lập tạo ra artifact giống hệt nhau theo từng byte. Để tiến gần mục tiêu đó, cần cố định JDK, build tool, plugin, dependency, cấu hình môi trường và các bước tạo artifact.

Với dự án Java 17, cần phân biệt ba lớp phiên bản:

1. **JDK chạy build:** JVM dùng để chạy Gradle/Maven và các plugin.
2. **JDK toolchain biên dịch/kiểm thử:** JDK mà compiler và test task sử dụng.
3. **Java release mục tiêu:** phiên bản ngôn ngữ, bytecode và API mà ứng dụng được phép dùng, thường đặt là `--release 17`.

Ba lớp này có liên quan nhưng không nhất thiết là cùng một cấu hình. Cố định `--release 17` không tự cố định JDK đang chạy build; khai báo Java toolchain 17 cũng không tự cố định phiên bản Gradle hoặc Maven.

Bài này trình bày cách thiết lập build ổn định với Gradle hoặc Maven, quản lý dependency, chuẩn hóa môi trường, tạo archive xác định và xác minh kết quả trên Java 17.

## 1. Phân biệt repeatable, reproducible và hermetic build

Các thuật ngữ thường được dùng gần nhau:

| Khái niệm | Ý nghĩa thực tế |
| --- | --- |
| Repeatable build | Có thể chạy lại quy trình build với cùng cấu hình và nhận kết quả tương đương. |
| Reproducible build | Các lần build độc lập từ cùng đầu vào được kiểm soát tạo artifact giống hệt nhau, thường kiểm tra bằng checksum. |
| Hermetic build | Build chỉ phụ thuộc vào các đầu vào được khai báo/kiểm soát, không vô tình phụ thuộc vào máy, mạng, file hoặc công cụ bên ngoài chưa được khai báo. |

Một build có thể chạy lại thành công nhưng chưa reproducible theo từng byte. Ví dụ, file JAR có cùng class và resource nhưng timestamp trong ZIP entry khác nhau, dẫn đến checksum khác.

Một build cũng có thể reproducible trong máy lập trình viên nhưng không hermetic: máy đó đang dùng một dependency trong cache hoặc một biến môi trường không được ghi nhận. Khi chạy trên CI sạch, kết quả có thể khác hoặc không build được.

Mục tiêu thực tế là tiến dần theo các lớp:

- Cùng source revision và cấu hình.
- Cùng JDK, build tool, plugin và dependency.
- Cùng môi trường cần thiết.
- Không có timestamp, thứ tự file hoặc dữ liệu ngẫu nhiên làm thay đổi artifact.
- Có thể build trên workspace sạch và so sánh checksum.

## 2. Cố định phiên bản JDK

JDK là một trong những đầu vào quan trọng nhất. Khác biệt giữa các phiên bản JDK có thể ảnh hưởng compiler, API, bytecode, annotation processor, runtime và công cụ đi kèm.

Với dự án mục tiêu Java 17, nên xác định rõ:

- Major version: Java 17.
- Nhà cung cấp JDK (vendor), nếu tổ chức cần chuẩn hóa.
- Bản cập nhật JDK cụ thể (patch/build) cho môi trường release.
- Kiến trúc hệ điều hành/CPU, nếu artifact hoặc tool phụ thuộc nền tảng.

Không nên chỉ ghi trong README rằng “cần Java 17” rồi để mỗi máy tự chọn bất kỳ JDK 17 nào. Các bản cập nhật khác nhau trong cùng major version thường tương thích, nhưng muốn build bit-for-bit thì vẫn cần cố định bản phân phối và build cụ thể.

### 2.1. Kiểm tra JDK đang được sử dụng

Chạy:

```bash
java -version
javac -version
```

Kiểm tra biến môi trường:

```bash
# Linux/macOS
echo "$JAVA_HOME"

# PowerShell
$env:JAVA_HOME
```

`java -version` cho biết runtime đang được tìm thấy qua PATH; `javac -version` cho biết compiler. Trong CI, cần kiểm tra cả hai và xác nhận build tool thực sự dùng đúng JDK.

### 2.2. Cố định JDK trong CI

CI nên cài hoặc chọn JDK 17 theo một phiên bản và vendor đã thống nhất. Ví dụ workflow dùng container image đã pin digest:

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    container:
      image: eclipse-temurin:17-jdk@sha256:<approved-image-digest>
    steps:
      - uses: actions/checkout@v4
      - name: Verify JDK
        run: |
          java -version
          javac -version
      - name: Build
        run: ./gradlew --no-daemon clean build
```

Tên image và digest ở đây là chỗ cần thay bằng image đã được tổ chức phê duyệt. Tag như `17-jdk` chỉ pin major line, có thể trỏ đến image mới ở lần tải sau. Digest pin nội dung image cụ thể. Nếu dùng runner cài JDK bằng action/setup tool, cũng nên chọn version cụ thể thay vì dùng nhãn động như `latest`.

Không nên commit đường dẫn tuyệt đối `JAVA_HOME` của máy cá nhân vào repository. Đường dẫn đó khác nhau giữa Windows, Linux, macOS và CI.

## 3. Phân biệt JDK chạy build, toolchain và release target

Một dự án Gradle có thể được khởi động bằng JDK mà Gradle daemon sử dụng, nhưng compiler/test task lại chạy bằng JDK toolchain được cấu hình.

Ví dụ:

- Gradle daemon chạy trên JDK 17.
- Java compilation dùng toolchain JDK 17.
- `--release 17` giới hạn API và bytecode mục tiêu ở Java 17.

Ba lớp này khác nhau:

| Thành phần | Kiểm soát điều gì? | Ví dụ |
| --- | --- | --- |
| JDK chạy build | JVM chạy Gradle/Maven và plugin. | JDK 17 đã pin trong CI image. |
| Java toolchain | JDK dùng cho compile/test task hỗ trợ toolchain. | Toolchain language version 17. |
| Release target | Ngôn ngữ, bytecode và API có thể dùng. | `--release 17`. |

Đặt `--release 17` rất quan trọng. Nếu chỉ đặt `sourceCompatibility = 17` và `targetCompatibility = 17`, compiler có thể vẫn nhìn thấy API từ JDK mới hơn nếu build chạy trên JDK mới. `--release` kiểm soát đồng thời language level, target class file và tập API công khai của release được chọn.

### 3.1. Kiểm tra bằng javac

Có thể biên dịch một file bằng:

```bash
javac --release 17 -encoding UTF-8 -d out src/main/java/com/example/Main.java
```

Điều này không thay thế build tool, nhưng minh họa rõ mục tiêu compiler.

## 4. Cố định Gradle bằng Gradle Wrapper

Gradle Wrapper giúp mọi developer và CI dùng cùng phiên bản Gradle mà dự án chỉ định. Repository nên chứa các file wrapper được tạo bởi Gradle:

```text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
```

File `gradle/wrapper/gradle-wrapper.properties` chứa phiên bản distribution:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.10.2-bin.zip
distributionSha256Sum=<verified-distribution-sha256>
```

Phiên bản trên chỉ là ví dụ minh họa về cách pin một phiên bản cụ thể; hãy chọn bản Gradle được dự án hỗ trợ và xác minh checksum chính thức trước khi dùng. Không thay bằng `gradle-8.x` hoặc URL trỏ tới bản phân phối thay đổi.

Checksum bảo vệ bước tải Gradle distribution khỏi việc nhận nội dung khác với bản đã phê duyệt. Không tự điền checksum bằng một giá trị đoán; lấy checksum từ nguồn phân phối chính thức hoặc quy trình phát hành đã được tin cậy.

Chạy build qua wrapper:

```bash
./gradlew --version
./gradlew clean build
```

Trên Windows:

```powershell
.\\gradlew.bat --version
.\\gradlew.bat clean build
```

Không yêu cầu developer cài Gradle global rồi gọi `gradle build`. Cách đó có thể chạy một phiên bản khác với phiên bản mà repository đã pin.

### 4.1. Pin Java toolchain trong Gradle

Trong `build.gradle` (Groovy DSL):

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}
```

Trong `build.gradle.kts` (Kotlin DSL):

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}
```

Toolchain cho phép Gradle chọn JDK phù hợp để chạy các task Java như compile và test. Nếu cần pin vendor, có thể khai báo thêm:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
        vendor.set(JvmVendorSpec.ADOPTIUM)
    }
}
```

Vendor constraint giới hạn nhà cung cấp, nhưng không tự pin patch/build cụ thể. Muốn tái tạo chính xác, vẫn cần chuẩn hóa JDK distribution/build trong CI hoặc môi trường build được quản lý.

### 4.2. Toolchain không đồng nghĩa Gradle daemon JVM

Java toolchain điều khiển JDK cho các task hỗ trợ toolchain. Gradle daemon vẫn chạy bằng một JVM riêng, thường được chọn từ `JAVA_HOME` hoặc cấu hình môi trường/Gradle.

Do đó, cần ghi rõ cả:

- JDK dùng để chạy Gradle.
- JDK toolchain dùng để compile/test.
- Java release mục tiêu.

Không commit `org.gradle.java.home` với đường dẫn tuyệt đối của máy lập trình viên. Nếu tổ chức cần cố định daemon JDK, hãy cấu hình tại môi trường CI/container hoặc cơ chế provisioning phù hợp với phiên bản Gradle đang dùng.

## 5. Cố định Maven bằng Maven Wrapper

Maven Wrapper có vai trò tương tự Gradle Wrapper: repository xác định phiên bản Maven mà build sử dụng.

Các file thường có:

```text
mvnw
mvnw.cmd
.mvn/wrapper/maven-wrapper.jar
.mvn/wrapper/maven-wrapper.properties
```

Ví dụ `.mvn/wrapper/maven-wrapper.properties`:

```properties
distributionUrl=https\://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
distributionSha256Sum=<verified-distribution-sha256>
```

Phiên bản Maven trong ví dụ là một phiên bản cố định minh họa. Chọn phiên bản được dự án hỗ trợ, xác minh checksum chính thức và commit wrapper files cùng cấu hình. Không dùng một URL tải không cố định hoặc dựa vào Maven cài global trên máy.

Chạy:

```bash
./mvnw --version
./mvnw clean verify
```

Trên Windows:

```powershell
.\\mvnw.cmd --version
.\\mvnw.cmd clean verify
```

### 5.1. Cố định compiler release trong Maven

Trong `pom.xml`, khai báo encoding và release rõ ràng:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
                <encoding>UTF-8</encoding>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Plugin version cần được pin chính xác, như ví dụ `3.13.0`. Khi nâng cấp, thay version có chủ đích và review thay đổi. Không để Maven tự chọn version plugin từ môi trường hoặc phụ thuộc vào implicit defaults khi muốn tái tạo build.

Có thể dùng Maven Toolchains Plugin và file `toolchains.xml` để chọn JDK cụ thể cho compiler/test plugin. File toolchains thường chứa đường dẫn cài JDK tại từng máy nên cần quản lý theo môi trường, không commit đường dẫn cá nhân vào source repository.

## 6. Cố định plugin và build logic

Dependency của ứng dụng không phải đầu vào duy nhất. Plugin build cũng có thể tải thư viện, chạy code và ảnh hưởng artifact.

### Với Gradle

Pin version của plugin trong `plugins` block:

```kotlin
plugins {
    java
    id("com.example.build-conventions") version "1.4.2"
}
```

Nếu dùng plugin nội bộ, hãy bảo đảm version của plugin và dependency mà nó sử dụng cũng được quản lý rõ. Tránh dùng version động hoặc plugin snapshot cho release build.

Có thể tập trung version dependency trong Version Catalog:

```toml
[versions]
jackson = "2.17.2"
junit = "5.11.0"

[libraries]
jackson-databind = {
    module = "com.fasterxml.jackson.core:jackson-databind",
    version.ref = "jackson"
}
junit-jupiter = {
    module = "org.junit.jupiter:junit-jupiter",
    version.ref = "junit"
}
```

Các version ở đây là ví dụ pin cụ thể, không phải khuyến nghị dùng nguyên xi cho mọi dự án. Hãy chọn phiên bản đã được kiểm tra về tương thích và bảo mật.

### Với Maven

Pin version của từng build plugin trong `pom.xml`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.2</version>
        </plugin>
    </plugins>
</build>
```

Khai báo version plugin tường minh giúp build không phụ thuộc vào version mặc định có thể thay đổi theo Maven super POM hoặc môi trường. Với plugin do dự án sử dụng, hãy pin và quản lý nâng cấp tương tự dependency runtime.

## 7. Cố định dependency và dependency graph

Một khai báo như `1.2.+`, `latest.release`, version range hoặc `SNAPSHOT` có thể phân giải thành version khác ở những lần build khác nhau. Điều đó làm thay đổi dependency graph dù source code không đổi.

Nên:

- Khai báo version cụ thể cho dependency trực tiếp.
- Quản lý version tập trung bằng Version Catalog hoặc Maven dependency management.
- Tránh version động, version range và snapshot trong release build.
- Kiểm soát repository được phép phân phối dependency.
- Theo dõi dependency bắc cầu (transitive dependencies).
- Lưu lại trạng thái dependency resolution theo cơ chế của build tool.

### 7.1. Gradle dependency locking

Gradle hỗ trợ dependency locking để ghi lại version đã được resolve cho các configuration được bật lock.

Ví dụ trong `build.gradle.kts`:

```kotlin
dependencyLocking {
    lockAllConfigurations()
}
```

Tạo hoặc cập nhật lock state khi resolve dependency:

```bash
./gradlew --write-locks build
```

Commit các lockfile do Gradle tạo ra vào repository. Khi dependency được nâng cấp có chủ đích, cập nhật lockfile cùng thay đổi version và review diff. Không tự sửa lockfile bằng tay nếu không hiểu cấu trúc và resolution của Gradle.

Dependency locking giúp cố định phiên bản đã resolve, bao gồm dependency bắc cầu ở những configuration được quản lý. Nó không tự xác minh byte của artifact tải về; dùng thêm dependency verification.

### 7.2. Gradle dependency verification

Gradle có thể xác minh checksum hoặc chữ ký của dependency. Khởi tạo metadata checksum:

```bash
./gradlew --write-verification-metadata sha256 build
```

Lệnh này resolve các dependency của task được chạy và tạo/cập nhật `gradle/verification-metadata.xml`. Review file rồi commit. Các lần build sau có thể kiểm tra artifact tải về có khớp checksum đã lưu không.

Khi thêm dependency hoặc nâng version, cập nhật verification metadata có kiểm soát. Không dùng chế độ ghi metadata như một thao tác tự động chấp nhận mọi artifact mới mà không review nguồn và checksum.

### 7.3. Maven dependency management

Maven cho phép quản lý version tập trung bằng `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit</groupId>
            <artifactId>junit-bom</artifactId>
            <version>5.11.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

BOM (Bill of Materials) giúp các dependency trong cùng hệ sinh thái dùng bộ version tương thích. Các version trong ví dụ là pin cụ thể; cần chọn BOM phù hợp với dự án.

Maven core không có workflow dependency lockfile tương đương Gradle dependency locking theo cùng cách. Để giữ dependency graph ổn định, pin version, tránh range/SNAPSHOT, quản lý BOM, kiểm tra dependency tree và kiểm soát repository/mirror.

Xem dependency graph:

```bash
./mvnw dependency:tree
```

Xem POM sau khi kế thừa và áp dụng profile:

```bash
./mvnw help:effective-pom
```

Lệnh giúp phát hiện version/plugin thực tế đến từ parent POM, profile hoặc super POM thay vì chỉ nhìn một phần `pom.xml`.

## 8. Cố định repository và nguồn artifact

Ngay cả khi version đã pin, repository vẫn là một đầu vào của build. Nên thống nhất repository/mirror mà CI và developer được phép sử dụng.

### Gradle

Khai báo repository có chủ đích:

```kotlin
repositories {
    mavenCentral()
}
```

Trong hệ thống doanh nghiệp, có thể dùng repository manager nội bộ làm mirror/proxy. Hạn chế repository tùy ý được khai báo trong từng subproject; tập trung cấu hình ở cấp phù hợp và kiểm soát plugin repositories riêng.

### Maven

Có thể cấu hình mirror trong `settings.xml` để mọi repository request đi qua repository manager đã phê duyệt. `settings.xml` thường là cấu hình môi trường/user, nên cần cung cấp thống nhất trong CI và tài liệu onboarding.

Không để một build phụ thuộc vào artifact chỉ tồn tại trong local Maven repository hoặc Gradle cache. Một build trên workspace sạch phải tải được toàn bộ đầu vào từ repository đã xác định.

## 9. Làm cho archive và artifact có nội dung xác định

Một file JAR là một ZIP archive. Nếu timestamp của entry, thứ tự file hoặc metadata thay đổi giữa hai lần build, checksum toàn bộ JAR có thể khác dù class bên trong giống nhau.

### 9.1. Maven: outputTimestamp

Maven Archiver hỗ trợ thuộc tính `project.build.outputTimestamp` để tạo archive có timestamp xác định.

Ví dụ:

```xml
<properties>
    <project.build.outputTimestamp>
        2024-01-01T00:00:00Z
    </project.build.outputTimestamp>
</properties>
```

Giá trị trên chỉ là timestamp cố định minh họa. Trong quy trình release, có thể lấy timestamp chuẩn từ source revision hoặc một giá trị release đã được xác định, miễn là mọi lần build của cùng source revision dùng đúng một giá trị.

Đảm bảo các plugin tạo JAR, source JAR, javadoc JAR hoặc ZIP khác cũng hỗ trợ và sử dụng cấu hình reproducible tương ứng.

### 9.2. Gradle: archive tasks

Gradle cung cấp các thuộc tính cho archive task để chuẩn hóa timestamp và thứ tự file:

```kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
```

`isPreserveFileTimestamps = false` loại bỏ timestamp nguồn không ổn định khỏi archive; `isReproducibleFileOrder = true` yêu cầu thứ tự file xác định. Các phiên bản Gradle hiện đại đã mặc định hướng tới archive reproducible, nhưng khai báo rõ có thể giúp người đọc hiểu chủ đích. Hãy xác nhận phiên bản Gradle dự án đang dùng hỗ trợ các thuộc tính này.

### 9.3. Generated files và manifest

Archive vẫn có thể khác nếu build tạo file chứa:

- Thời điểm hiện tại.
- Username hoặc hostname của máy build.
- Đường dẫn workspace tuyệt đối.
- Số build CI tăng dần.
- Nội dung lấy từ API ngoài hoặc môi trường không được pin.
- Thứ tự phần tử không xác định từ map/set hoặc tác vụ chạy song song.

Nếu cần đưa metadata build vào artifact, hãy chọn các giá trị có tính xác định, ví dụ source commit ID, version release và timestamp được quản lý. Không chèn `new Date()` hoặc `Instant.now()` vào resource nếu mục tiêu là cùng source revision tạo ra cùng artifact.

## 10. Chuẩn hóa encoding, locale, timezone và environment

Build có thể phụ thuộc vào môi trường hệ điều hành:

- Encoding mặc định khi đọc/ghi text.
- Locale ảnh hưởng format số, ngày tháng hoặc sort.
- Timezone ảnh hưởng timestamp được tạo.
- Biến môi trường ảnh hưởng profile, endpoint, version hoặc nội dung generated file.
- Line ending và filesystem behavior có thể khác giữa Windows/Linux.
- Path tuyệt đối và thứ tự duyệt file có thể khác.

### 10.1. Khai báo encoding rõ ràng

Với Maven:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
    <maven.compiler.encoding>UTF-8</maven.compiler.encoding>
</properties>
```

Với Gradle:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
```

Trong code, khi chuyển byte và text, ưu tiên chỉ rõ charset:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);
```

Không dựa vào charset mặc định của máy khi nội dung đó đi vào artifact.

### 10.2. Chuẩn hóa timezone và locale

Nếu build tạo file có ngày giờ hoặc format theo locale, đặt môi trường nhất quán trong CI, ví dụ:

```bash
export TZ=UTC
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
./gradlew clean build
```

Tên locale có thể khác trên một số image/hệ điều hành. Hãy bảo đảm locale đã được cài trong image và build script không giả định một locale không tồn tại.

Tốt hơn nữa, nếu logic không cần timezone/locale mặc định, hãy truyền rõ `ZoneId` và `Locale` vào API thay vì dựa vào default toàn process.

### 10.3. Chuẩn hóa line ending và file nguồn

Có thể dùng `.gitattributes` để quy định line ending cho các loại file văn bản:

```text
* text=auto
*.java text eol=lf
*.gradle text eol=lf
*.gradle.kts text eol=lf
*.xml text eol=lf
*.properties text eol=lf
```

Quy tắc line ending giúp giảm khác biệt không cần thiết giữa môi trường Windows và Unix. Với script cần CRLF hoặc file nhị phân, khai báo riêng phù hợp.

## 11. Làm cho test và code generation xác định

Ngay cả khi compiler và dependency đã pin, test hoặc generator có thể làm build không ổn định.

Các nguyên nhân thường gặp:

- Test dựa vào đồng hồ thật hoặc timezone mặc định.
- Test dùng random seed thay đổi mỗi lần.
- Test phụ thuộc thứ tự thực thi hoặc dữ liệu chia sẻ giữa test.
- Test gọi dịch vụ bên ngoài có dữ liệu thay đổi.
- Annotation processor hoặc generator ghi timestamp vào file.
- Task lấy dữ liệu từ network mà không pin snapshot.
- Code duyệt collection không có thứ tự xác định rồi ghi ra file.

Nên:

- Dùng `Clock.fixed()` khi kiểm thử logic thời gian.
- Dùng random seed cố định trong test cần tính lặp lại.
- Sắp xếp dữ liệu trước khi serialize hoặc ghi file nếu thứ tự có ý nghĩa.
- Mock hoặc dùng service thử nghiệm có dữ liệu cố định thay vì gọi API công cộng.
- Cố định version annotation processor và plugin code generation.
- Không dùng thời gian hiện tại làm nội dung generated source nếu không cần thiết.

Ví dụ test thời gian:

```java
Clock clock = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneOffset.UTC
);
```

Khi mọi test nhận cùng một clock cố định, kết quả không phụ thuộc ngày chạy test.

## 12. Kiểm soát network và build offline

Một build hoàn toàn offline có thể giúp kiểm tra xem mọi dependency đã được cache, nhưng chạy offline không tự bảo đảm build reproducible. Nếu cache chứa artifact không đúng hoặc build dựa vào dependency động, kết quả vẫn có thể khác giữa máy.

Với Gradle:

```bash
./gradlew --offline clean build
```

Với Maven:

```bash
./mvnw -o clean verify
```

Các lệnh trên yêu cầu dependency đã có trong cache. Chúng hữu ích để phát hiện build vô tình cần truy cập mạng ở giai đoạn build, nhưng release build vẫn cần quy trình tải dependency từ repository đã kiểm soát, xác minh checksum và lưu trữ đầu vào đáng tin cậy.

Không để task compile/test gọi endpoint bên ngoài để sinh source hoặc tải dữ liệu không version hóa. Nếu một task cần đầu vào từ network, hãy biến dữ liệu đó thành artifact có version/checksum và khai báo rõ như một dependency.

## 13. Build trong CI với cùng quy trình như developer

Một pipeline CI nên dùng wrapper của repository, kiểm tra JDK và chạy cùng task mà developer có thể chạy local.

Ví dụ Gradle:

```yaml
steps:
  - uses: actions/checkout@v4

  - name: Verify Java
    run: |
      java -version
      javac -version

  - name: Verify Gradle wrapper
    run: ./gradlew --version

  - name: Build and test
    run: ./gradlew --no-daemon clean build
```

Ví dụ Maven:

```yaml
steps:
  - uses: actions/checkout@v4

  - name: Verify Java and Maven
    run: |
      java -version
      javac -version
      ./mvnw --version

  - name: Build and test
    run: ./mvnw --batch-mode --no-transfer-progress clean verify
```

Các action của CI cũng là đầu vào. Với pipeline yêu cầu supply-chain control nghiêm ngặt, pin action theo commit SHA đã được review thay vì chỉ dùng tag có thể thay đổi. Tương tự, pin container image theo digest và kiểm soát tool cài thêm trong job.

CI nên chạy trên workspace sạch hoặc checkout mới để không vô tình dùng file generated/cached từ lần chạy trước. Cache dependency có thể giúp nhanh hơn, nhưng không được trở thành nguồn duy nhất của một artifact không xác minh.

## 14. Xác minh hai lần build có giống nhau

Build thành công hai lần chưa chứng minh artifact giống nhau. Hãy so sánh checksum của file đầu ra.

### 14.1. Linux/macOS

```bash
sha256sum build/libs/app.jar
```

Hoặc trên macOS:

```bash
shasum -a 256 build/libs/app.jar
```

### 14.2. Windows PowerShell

```powershell
Get-FileHash .\\build\\libs\\app.jar -Algorithm SHA256
```

Maven thường đặt JAR trong `target/`; Gradle Java plugin thường đặt trong `build/libs/`.

Để kiểm tra thực sự, cần tạo artifact từ hai lần build độc lập:

1. Checkout cùng source commit vào hai workspace sạch.
2. Dùng cùng JDK distribution/build, wrapper, plugin và dependency.
3. Dùng cùng cấu hình environment đã quy định.
4. Chạy cùng lệnh build.
5. So sánh SHA-256 của artifact.

Nếu checksum khác, so sánh nội dung archive:

```bash
jar tf app.jar
```

Giải nén hai artifact vào hai thư mục riêng rồi so sánh file. Nếu class/resource giống nhau nhưng JAR khác checksum, kiểm tra timestamp, thứ tự ZIP entry, manifest hoặc metadata archive. Nếu nội dung file khác, kiểm tra code generation, dependency resolution, encoding, locale/timezone và các biến môi trường.

## 15. Một ví dụ cấu hình Gradle Java 17 có tính lặp lại

Ví dụ `build.gradle.kts` tổng hợp một số nguyên tắc:

```kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

plugins {
    java
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.0")
}

tasks.test {
    useJUnitPlatform()
}

dependencyLocking {
    lockAllConfigurations()
}
```

Trong ví dụ này:

- Toolchain yêu cầu JDK 17 cho các task Java.
- `options.release` giới hạn API và bytecode mục tiêu ở Java 17.
- Encoding được cố định là UTF-8.
- Archive task tắt timestamp nguồn và dùng thứ tự file xác định.
- Dependency có version cụ thể.
- Dependency locking được bật cho các configuration.

Sau đó chạy build để tạo lock state và verification metadata theo quy trình của dự án, rồi commit các file tương ứng. Cần pin Gradle Wrapper và JDK chạy daemon ở môi trường CI như các phần trước.

## 16. Một ví dụ cấu hình Maven Java 17 có tính lặp lại

Ví dụ các phần chính trong `pom.xml`:

```xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>app</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <!-- Pin version cụ thể cho dependency -->
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <encoding>UTF-8</encoding>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Đây là khung minh họa, cần thêm dependency và plugin đúng với dự án. Pin Maven Wrapper, compiler plugin, các plugin test/package và dependency bắc cầu. Giá trị output timestamp phải được quản lý nhất quán cho cùng source revision; không cập nhật ngẫu nhiên giữa hai lần build.

Maven không cung cấp dependency lockfile built-in theo cách giống Gradle locking, nên cần đặc biệt chú ý version tường minh, BOM, repository và kiểm tra `dependency:tree` cùng `effective-pom`.

## 17. Quy trình thiết lập reproducible build cho dự án hiện có

Có thể triển khai theo thứ tự sau để dễ xác định nguyên nhân khi có khác biệt:

1. **Ghi nhận baseline:** commit source hiện tại, build một lần và lưu checksum artifact.
2. **Pin JDK:** chọn vendor/build Java 17 và xác nhận `java -version`, `javac -version`.
3. **Pin build tool:** commit Gradle Wrapper hoặc Maven Wrapper và checksum distribution.
4. **Pin compiler target:** cấu hình `--release 17`.
5. **Pin plugin:** khai báo version cụ thể cho mọi plugin build.
6. **Pin dependency:** loại bỏ version động, range và snapshot khỏi release build; quản lý transitive dependency.
7. **Bật xác minh:** với Gradle, dùng locking và dependency verification; với Maven, kiểm tra effective POM, dependency tree và repository policy.
8. **Chuẩn hóa archive:** timestamp, thứ tự file và metadata generated.
9. **Chuẩn hóa environment:** encoding, locale, timezone, path, container và biến môi trường.
10. **Kiểm thử trên workspace sạch:** chạy cùng lệnh trong hai môi trường độc lập.
11. **So sánh checksum:** điều tra mọi khác biệt trước khi công bố artifact.

Đừng thay đổi tất cả các biến cùng lúc. Khi checksum khác, thay đổi từng nhóm cấu hình giúp khoanh vùng nhanh hơn.

## 18. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
| --- | --- |
| Khai báo `sourceCompatibility = 17` là đủ cố định build. | Cần cố định JDK/toolchain và dùng `--release 17` để giới hạn API mục tiêu. |
| Dùng Java 17 là mọi bản JDK 17 tạo artifact giống nhau. | Vendor, patch/build, compiler, plugin và môi trường có thể ảnh hưởng kết quả. |
| Cài Gradle/Maven global là đủ. | Wrapper pin build tool theo repository và giúp CI/developer dùng cùng version. |
| Pin dependency trực tiếp là đủ. | Dependency bắc cầu và plugin cũng là đầu vào cần kiểm soát. |
| Build chạy hai lần thành công là reproducible. | Cần so sánh artifact, tốt nhất bằng checksum từ workspace độc lập. |
| Chạy offline tự động bảo đảm reproducible. | Offline chỉ giới hạn network; cache vẫn có thể chứa đầu vào khác hoặc không được xác minh. |
| JAR khác checksum chắc chắn class khác nhau. | Timestamp, ZIP entry order và metadata cũng có thể làm archive khác. |
| Chỉ CI cần pin JDK. | Developer và CI cần dùng quy trình tương thích; nếu không, lỗi có thể chỉ xuất hiện ở một môi trường. |
| Mọi biến môi trường đều phải cố định giống nhau. | Chỉ những biến ảnh hưởng build cần được chuẩn hóa hoặc khai báo; secret và môi trường triển khai cần được quản lý riêng. |

## 19. Bài thực hành

### Bài 1 — xác định đầu vào build

Liệt kê JDK, Gradle/Maven, plugin, dependency, repository, environment variables và container image mà dự án đang sử dụng. Phân biệt đầu vào nào đã pin và đầu vào nào còn thay đổi.

### Bài 2 — cố định Java release

Cấu hình Gradle hoặc Maven để compile bằng Java 17 và dùng `--release 17`. Thử gọi một API chỉ có ở JDK mới hơn để xác nhận compiler từ chối.

### Bài 3 — dùng Wrapper

Chạy `./gradlew --version` hoặc `./mvnw --version`. Xác nhận build tool version khớp cấu hình wrapper trong repository. Không dùng lệnh build tool global.

### Bài 4 — pin dependency

Tìm version động, range và snapshot trong build files. Thay bằng version cụ thể đã được review. Với Gradle, bật dependency locking và tạo lockfile. Tạo verification metadata SHA-256 và commit sau khi review.

### Bài 5 — chuẩn hóa archive

Cấu hình archive task hoặc `project.build.outputTimestamp`. Build hai lần từ cùng source trong hai workspace riêng và so sánh SHA-256.

### Bài 6 — tìm nguồn khác biệt

Nếu checksum không khớp, so sánh nội dung JAR, manifest, timestamp ZIP entry và generated resource. Kiểm tra locale, timezone, encoding, username, hostname và source path có bị ghi vào artifact không.

### Bài 7 — thiết lập CI sạch

Tạo job CI dùng JDK 17 đã pin, wrapper, cùng build command với developer. Chạy trên checkout mới, ghi lại JDK/build tool version và lưu checksum artifact.

## 20. Ghi nhớ nhanh

| Thành phần | Cách cố định |
| --- | --- |
| JDK chạy build | Chọn vendor/build cụ thể trong CI hoặc container image đã pin digest. |
| Java compile/test toolchain | Gradle `java.toolchain` hoặc Maven Toolchains. |
| API/bytecode mục tiêu | `--release 17`. |
| Gradle | Gradle Wrapper với distribution version và SHA-256. |
| Maven | Maven Wrapper với distribution version và SHA-256. |
| Build plugins | Pin version cụ thể, review khi nâng cấp. |
| Dependency | Version cụ thể, BOM/version catalog và quản lý transitive graph. |
| Gradle dependency state | Dependency locking và verification metadata. |
| Maven dependency state | Dependency management, effective POM, dependency tree và repository policy. |
| Archive | Timestamp và file order xác định. |
| Text resources | UTF-8, line ending và locale/timezone rõ ràng. |
| Test/code generation | Clock, random seed và đầu vào xác định; tránh network phụ thuộc dữ liệu thay đổi. |
| Xác minh kết quả | Build trên workspace độc lập và so sánh SHA-256. |

**Nguyên tắc cốt lõi:** Muốn build Java 17 có thể tái tạo, hãy coi JDK, build tool, plugin, dependency và môi trường là những đầu vào cần được pin và kiểm soát. Wrapper cố định Gradle/Maven; toolchain chọn JDK cho compile/test; `--release 17` cố định API mục tiêu; dependency locking/verification và archive metadata giảm khác biệt giữa các lần chạy. Cuối cùng, chỉ checksum của artifact được tạo từ những workspace độc lập mới cung cấp bằng chứng trực tiếp rằng build đang reproducible.

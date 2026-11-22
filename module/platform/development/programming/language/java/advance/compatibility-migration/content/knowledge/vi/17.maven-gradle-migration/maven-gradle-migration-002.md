# Maven Wrapper, Gradle Wrapper và phiên bản được cố định trong dự án

Khi nâng một dự án Java lên JDK mới, lệnh `mvn clean verify` hoặc `gradle build` không nhất thiết cho cùng kết quả trên hai máy. Một lập trình viên có Maven 3.x cài từ nhiều năm trước; một máy khác có bản Maven mới hơn; CI có thể dùng bản Gradle mặc định của build image. Build script, plugin, compiler và cách dependency được resolve có thể thay đổi theo phiên bản công cụ.

**Maven Wrapper** và **Gradle Wrapper** đưa lựa chọn phiên bản công cụ vào chính repository. Developer và pipeline dùng script đi kèm dự án, còn cấu hình Wrapper chỉ rõ bản Maven/Gradle sẽ được tải hoặc sử dụng. Đây là nền tảng của build có thể tái tạo trong quá trình Java Advance Compatibility Migration, nhưng chưa đủ: Wrapper không tự khóa JDK, Java source/bytecode target, plugin, dependency hoặc runtime production.

Bài học trình bày cách dùng hai Wrapper, vị trí phiên bản được cố định, sự khác biệt giữa tool và JDK, quy trình nâng cấp có kiểm soát, tích hợp CI, bảo mật chuỗi cung ứng và các tình huống lỗi thường gặp.

## 1. Wrapper giải quyết bài toán gì?

Một repository Java có thể được build bằng công cụ đã cài sẵn trong máy:

~~~bash
mvn clean verify
gradle clean build
~~~

Cách này dựa vào biến `PATH`, cài đặt hệ điều hành và môi trường của người chạy. Nếu phiên bản Maven/Gradle không thống nhất, kết quả có thể khác nhau.

Với Wrapper, repository cung cấp launcher:

~~~bash
# Linux / macOS:
./mvnw clean verify
./gradlew clean build

# Kiểm tra phiên bản được chọn:
./mvnw --version
./gradlew --version
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd clean verify
.\gradlew.bat clean build

.\mvnw.cmd --version
.\gradlew.bat --version
~~~

Wrapper không phải Maven hoặc Gradle thứ hai. Nó là cơ chế bootstrap và khởi chạy **Maven/Gradle distribution được dự án chọn**. Một repository Maven thông thường dùng `mvnw`; một repository Gradle dùng `gradlew`.

Ba lợi ích chính:

1. **Tính nhất quán:** cùng commit thường dẫn đến cùng phiên bản build tool.
2. **Onboarding:** developer mới không cần tự đoán nên cài Maven/Gradle phiên bản nào.
3. **Quản trị thay đổi:** nâng build tool được ghi thành thay đổi có thể review và rollback trong Git.

Ba giới hạn quan trọng:

1. Wrapper không tự chọn đúng JDK để chạy build nếu môi trường/toolchain chưa được cấu hình.
2. Wrapper không khóa tất cả transitive dependencies hoặc build plugins.
3. Wrapper không bảo đảm build reproducible trong mọi OS, CPU, locale, timezone hoặc môi trường mạng.

## 2. Phân biệt bốn phiên bản khác nhau

Trong quá trình migration Java, không được gộp tất cả vào một trường `javaVersion`.

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Maven/Gradle version | Maven 3.9.x / Gradle 8.x | Build tool và build DSL/runtime |
| JDK chạy build | JDK 21 | JVM chạy Maven/Gradle, plugin hoặc build logic |
| JDK toolchain | JDK 21 | JDK thực thi Java compiler hay task Java liên quan |
| Java release target | `--release 17` | Cú pháp, Java SE API và bytecode target của ứng dụng |

Ví dụ: Gradle chạy bằng JDK 21, JavaCompile task cũng dùng JDK 21, nhưng `options.release = 17` yêu cầu ứng dụng sử dụng Java 17 source/API/bytecode baseline. Wrapper chỉ quyết định **Gradle version**.

Một tình huống khác: Gradle daemon chạy JDK 17 nhưng toolchain biên dịch có thể chọn JDK 21 nếu phiên bản Gradle và cấu hình hỗ trợ. Khi đó phải kiểm tra riêng test runtime để biết artifact có thực sự chạy trên phiên bản Java thấp nhất cần hỗ trợ hay không.

Không suy ra ứng dụng tương thích Java 17 chỉ vì `./gradlew --version` cho thấy Gradle hỗ trợ Java 17.

## 3. Maven Wrapper: cấu trúc và cấu hình

Một dự án Maven có thể có:

~~~text
maven-project/
├── pom.xml
├── mvnw
├── mvnw.cmd
└── .mvn/
    ├── maven.config
    ├── jvm.config
    └── wrapper/
        ├── maven-wrapper.properties
        └── maven-wrapper.jar    # Có thể có, tùy chế độ Wrapper
~~~

Vai trò từng thành phần:

- `mvnw` và `mvnw.cmd`: launcher cho shell Unix và Windows.
- `.mvn/wrapper/maven-wrapper.properties`: metadata xác định Maven distribution, nguồn tải và cấu hình Wrapper tương ứng.
- `maven-wrapper.jar`: bootstrap JAR ở một số chế độ; có cấu hình wrapper dùng script mà không cần commit JAR này.
- `.mvn/maven.config`: arguments mặc định cho lệnh Maven nếu dự án dùng.
- `.mvn/jvm.config`: các JVM arguments Maven dùng; không tự cài đặt bản JDK.

Không mặc định mọi Maven Wrapper có đúng cùng một cấu trúc file. Maven Wrapper plugin có những chế độ phân phối và bootstrap khác nhau tùy phiên bản.

### 3.1. Distribution URL cố định Maven version

Ví dụ `.mvn/wrapper/maven-wrapper.properties`:

~~~properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
~~~

Đây là ví dụ dùng Maven 3.9.9 để minh họa nơi cố định phiên bản, **không phải tuyên bố bản mới nhất hoặc bắt buộc**. Trong dự án thật, phải chọn Maven version theo ma trận tương thích với JDK và plugins.

Một số wrapper configuration hỗ trợ checksum, wrapper download URL hoặc tuỳ chọn khác. Tên thuộc tính và hành vi phải được đối chiếu với **phiên bản Maven Wrapper cụ thể** chứ không copy vô điều kiện từ một template.

### 3.2. Tạo Maven Wrapper

Nếu môi trường đã có Maven và Maven Wrapper plugin thích hợp:

~~~bash
mvn wrapper:wrapper -Dmaven=3.9.9
~~~

Lệnh tạo hoặc cập nhật các file Wrapper theo phiên bản plugin được resolve. Tham số và cách chọn plugin version có thể thay đổi, nên dự án cần kiểm tra hướng dẫn chính thức cho wrapper plugin đang dùng.

Sau đó chạy:

~~~bash
./mvnw --version
./mvnw -B clean verify
~~~

`-B` bật batch mode phù hợp CI. Khi wrapper đã được commit, build thông thường nên gọi `./mvnw`, không dùng Maven toàn cục tùy tiện.

## 4. Gradle Wrapper: cấu trúc và cấu hình

Một Gradle project thường có:

~~~text
gradle-project/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
└── gradle/
    ├── libs.versions.toml
    └── wrapper/
        ├── gradle-wrapper.jar
        └── gradle-wrapper.properties
~~~

Có thể dùng Groovy DSL `settings.gradle` / `build.gradle` thay vì Kotlin DSL `.kts`.

- `gradlew` và `gradlew.bat`: launcher.
- `gradle-wrapper.jar`: bootstrap code đọc cấu hình và chạy Gradle.
- `gradle-wrapper.properties`: distribution URL và tuỳ chọn tải.
- `libs.versions.toml`: version catalog, nếu dự án sử dụng; nó quản lý khai báo plugin/dependency, **không tự chọn Gradle distribution version**.
- `build.gradle`: cấu hình plugins, source sets, tasks và dependencies.

### 4.1. Ví dụ gradle-wrapper.properties

~~~properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.10.2-bin.zip
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
~~~

`8.10.2` là số phiên bản ví dụ. Dự án cần chọn bản Gradle hỗ trợ JDK đích, plugin và toolchain dự kiến.

`distributionUrl` xác định distribution. Đuôi `-bin.zip` là bản thông thường để chạy build; `-all.zip` bổ sung tài liệu/nguồn cho các tình huống cần thiết. Các tuỳ chọn `networkTimeout`, `validateDistributionUrl` được hỗ trợ tùy phiên bản Wrapper; không mặc định script rất cũ sẽ đọc đầy đủ mọi property mới.

Khi wrapper hỗ trợ, có thể khai báo checksum:

~~~properties
distributionSha256Sum=<SHA256_DA_XAC_MINH_CUA_DISTRIBUTION>
~~~

Đây là placeholder, không thể dùng trực tiếp. Cần điền checksum chính xác lấy từ nguồn tin cậy. Checksum giúp phát hiện distribution bị thay đổi ngoài dự kiến.

### 4.2. Tạo hoặc nâng Gradle Wrapper

Nếu máy đã có Gradle:

~~~bash
gradle wrapper --gradle-version 8.10.2 --distribution-type bin
~~~

Khi repository đã có Wrapper:

~~~bash
./gradlew wrapper --gradle-version 8.10.2 --distribution-type bin
~~~

Sau khi nâng, cần kiểm tra **cả scripts, wrapper JAR và properties**. Trong quy trình Gradle phù hợp, chạy lại wrapper task sau khi distribution mới đã được kích hoạt có thể cần thiết để cập nhật đầy đủ các bootstrap files.

Chỉ sửa `distributionUrl` thủ công có thể đổi version distribution nhưng vẫn để lại launcher/JAR cũ; điều đó bỏ sót cập nhật chức năng và bảo mật của wrapper bootstrap.

## 5. Những file Wrapper nên được commit

Wrapper nên là một phần của repository để developer và CI dùng chung commit, không chỉ là thiết lập của một máy.

Với Maven:

~~~text
mvnw
mvnw.cmd
.mvn/wrapper/maven-wrapper.properties
.mvn/wrapper/maven-wrapper.jar   # chỉ nếu chế độ wrapper có file này
~~~

Với Gradle:

~~~text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
~~~

Không commit bản Maven/Gradle distribution đã tải hoặc toàn bộ cache của developer. Với Unix, scripts cần executable bit:

~~~bash
chmod +x mvnw
chmod +x gradlew

git add mvnw gradlew
~~~

Không bắt buộc cùng repository phải có cả `mvnw` lẫn `gradlew`; đoạn lệnh minh họa cách đánh dấu file script nếu có.

### 5.1. Đừng bỏ qua binary wrapper JAR

Gradle Wrapper JAR là mã thực thi được repository cung cấp. Một thay đổi `gradle-wrapper.jar` từ pull request có thể chạy trước khi build tool bắt đầu. Cần xác minh nguồn wrapper JAR và review thay đổi binary/script theo quy trình bảo mật.

Maven Wrapper cũng có bootstrap files cần được kiểm tra tương tự nếu dự án dùng.

## 6. Cách Wrapper tải và cache distribution

Về nguyên tắc:

~~~text
./mvnw hoặc ./gradlew
          |
          v
Đọc wrapper.properties
          |
          v
Distribution đúng version đã được cache?
          |
     +----+----+
     |         |
    Có       Không
     |         |
     |         v
     |     Download distribution
     |         |
     |         v
     |     Checksum/validation (nếu cấu hình hỗ trợ)
     |         |
     |         v
     |       Cache
     +----+----+
          |
          v
Khởi chạy Maven/Gradle
~~~

Máy developer đã build trước có thể dùng distribution cache. Một CI runner mới có thể phải tải lại. Do đó, build xanh trên máy dùng cache không bảo đảm build từ máy sạch sẽ thành công khi thiếu proxy, TLS truststore hoặc mirror.

Phân biệt:

- **Wrapper distribution cache:** chứa Maven/Gradle đã tải.
- **Dependency cache:** chứa libraries/plugins được Maven/Gradle resolve.
- **Compiler/JDK toolchain cache:** có thể chứa JDK được provisioning theo cấu hình phù hợp.
- **Build cache:** chứa outputs của tasks để tăng tốc.

Xóa một loại cache không có nghĩa đã xóa những loại khác. Không dùng thao tác xóa toàn bộ cache như bước “sửa lỗi” mặc định khi chưa biết nguyên nhân.

## 7. Wrapper không tự khóa dependency hoặc plugin

Cùng Maven version vẫn có thể resolve dependency khác nhau nếu POM dùng SNAPSHOT, version range hoặc repository metadata thay đổi. Tương tự, Gradle dùng dynamic version có thể lấy artifact mới:

~~~groovy
dependencies {
    implementation 'com.example:client:2.+'
}
~~~

`2.+` không phải version pin. Thời điểm build và cache có thể ảnh hưởng resolved version.

Cần tách:

| Nhóm version | Maven | Gradle |
|---|---|---|
| Build tool | Wrapper properties | Wrapper properties |
| Build plugins | `pluginManagement` và plugin `<version>` | `plugins`, `pluginManagement`, version catalog |
| Direct dependencies | POM properties, dependencyManagement, BOM | Dependency declarations, platforms/catalog |
| Transitive dependencies | Mediation, BOM, effective POM | Constraints, conflict resolution, locking |
| JDK build | JVM dùng chạy Maven | JVM dùng chạy Gradle daemon |
| Compiler | Compiler plugin, toolchain | Java toolchain, JavaCompile |
| Java target | `maven.compiler.release` | `options.release` |

### 7.1. Maven dependencyManagement

Trong Maven, một BOM có thể kiểm soát một nhóm versions:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.example</groupId>
      <artifactId>example-bom</artifactId>
      <version>1.2.3</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
~~~

Đây là ví dụ cấu trúc, không phải dependency cần dùng thật. Kiểm tra resolved dependencies bằng:

~~~bash
./mvnw dependency:tree
./mvnw help:effective-pom
~~~

Plugin phiên bản cụ thể có thể cần được resolve. Kết quả phải được gắn với đúng POM, Maven version và repository state.

### 7.2. Gradle version catalog khác lockfile

Một ví dụ `gradle/libs.versions.toml`:

~~~toml
[versions]
logging = "2.0.1"

[libraries]
logging-api = { module = "org.example:logging-api", version.ref = "logging" }
~~~

Version catalog tập trung hóa khai báo. Nó không mặc định khóa toàn bộ transitive versions. Nếu dự án cần dependency locking:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Sau khi cấu hình và resolve các configurations thích hợp, có thể dùng cơ chế `--write-locks` của Gradle theo tài liệu của đúng version. Lockfiles nên được review và commit.

Gradle dependency verification có thể bổ sung metadata hash/signature cho dependencies. Đây là tầng khác với checksum của **Gradle distribution** trong Wrapper.

## 8. Maven Wrapper không tự chọn JDK

`./mvnw` khởi Maven distribution, nhưng JVM thực thi Maven thường đến từ `JAVA_HOME` và môi trường launcher. Kiểm tra:

~~~bash
./mvnw --version
java -version
echo "$JAVA_HOME"
~~~

Output `./mvnw --version` cho biết Maven version và Java runtime/home được Maven dùng. Điều này quan trọng hơn suy đoán từ dòng `java -version` ở một terminal có cấu hình khác.

### 8.1. Compiler release

Ví dụ `pom.xml`:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Với Maven Compiler Plugin hỗ trợ, thuộc tính này đặt Java release target cho compilation. Nó **không** có nghĩa Maven JVM đang là JDK 17.

Ví dụ plugin:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <version>3.13.0</version>
  <configuration>
    <release>17</release>
  </configuration>
</plugin>
~~~

Version plugin là ví dụ minh họa, không phải yêu cầu dùng đúng bản này. Chọn bản thực tế theo ma trận Maven/JDK.

### 8.2. Maven Toolchains

Maven Toolchains cho phép một số plugin/task chọn JDK khác với JVM chạy Maven, nếu plugin hỗ trợ toolchain.

~~~text
Maven Wrapper version
        |
        v
JDK chạy Maven
        |
        v
Maven Compiler Plugin
        |
        v
Toolchain JDK biên dịch
        |
        v
--release 17
~~~

Một số plugins có thể không dùng toolchain và tiếp tục chạy trong JVM Maven. Vì vậy phải xác nhận compiler và các task cụ thể thực sự chọn JDK nào, không chỉ nhìn toolchain XML.

## 9. Gradle Wrapper khác Gradle JVM và Java toolchain

Với Gradle, ba thứ cần phân biệt:

- **Gradle distribution version:** từ Wrapper.
- **Gradle JVM/daemon:** JDK chạy build logic và plugins.
- **Java toolchains:** JDK cụ thể dùng để compile, test hoặc chạy các task có hỗ trợ.

Kiểm tra:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
~~~

`javaToolchains` có trong môi trường Gradle/Java plugin phù hợp; giúp xem các JDK installations được phát hiện.

Ví dụ Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Dự án chọn JDK 21 cho compilation nhưng giới hạn Java source/API/bytecode về Java 17. Điều đó không tự bảo đảm mọi third-party dependency đều chạy trên Java 17: cần kiểm tra bytecode và API của dependencies, cùng runtime tests.

Một phiên bản Gradle có thể hỗ trợ **dùng JDK N làm toolchain** trước hoặc sau mốc nó hỗ trợ **chạy Gradle daemon trên JDK N**. Luôn kiểm tra riêng hai khả năng.

### 9.1. Daemon sau khi đổi JDK

Nếu đổi JDK mà một daemon cũ vẫn tồn tại, có thể dừng daemon theo nhu cầu điều tra:

~~~bash
./gradlew --stop
./gradlew --version
~~~

Đây chỉ là bước quản lý daemon. Nó không chữa được plugin lỗi, wrapper quá cũ hoặc toolchain cấu hình sai.

## 10. Tại sao nâng Wrapper có thể làm build lỗi?

### Maven

Sau khi nâng Maven distribution:

- Compiler plugin quá cũ có thể không hiểu release target mới.
- Surefire/Failsafe hoặc provider test không hỗ trợ JDK mới.
- Plugin packaging, code generation, bytecode manipulation hoặc shading có thể sử dụng API cũ.
- Dependency resolution/settings.xml/mirror policy có thể bộc lộ khác biệt.
- Custom Maven extensions hoặc build agents có thể không tương thích.

### Gradle

Sau khi nâng Gradle:

- Custom Gradle plugin sử dụng API đã bị bỏ.
- Groovy/Kotlin DSL hoặc buildSrc logic cần cập nhật.
- Plugin Spring/Android/Kotlin hoặc instrumentation có ma trận hỗ trợ riêng.
- Compiler/annotation processor có thể không hiểu classfile target mới.
- Defaults, caching và dependency resolution có thể thay đổi theo bản Gradle.

Do đó **nâng Wrapper thành công không đồng nghĩa build thành công**. Phải kiểm thử plugins và tasks với đúng phiên bản JDK mong muốn.

## 11. Quy trình nâng Maven Wrapper có kiểm soát

### Bước 1: Chốt baseline

~~~bash
./mvnw --version
./mvnw -B clean verify
~~~

Ghi Maven version, Java version/home, compiler target, plugin versions, dependency graph và artifact output. Nếu build đã lỗi ở baseline, ghi rõ lỗi trước khi thay đổi.

### Bước 2: Chọn phiên bản Maven

Đối chiếu với JDK target, các plugin quan trọng và chính sách hỗ trợ. Không mặc định bản mới nhất luôn phù hợp với mọi dự án cũ.

### Bước 3: Cập nhật Wrapper

Ví dụ:

~~~bash
mvn wrapper:wrapper -Dmaven=3.9.9
~~~

Khi dùng version/plugin khác, tuân theo tài liệu của Maven Wrapper tương ứng. Review script, properties và bootstrap files.

### Bước 4: Chạy build bằng Wrapper mới

~~~bash
./mvnw --version
./mvnw -B clean verify
~~~

Nếu lỗi plugin, xác định plugin và nâng ở thay đổi riêng khi có thể.

### Bước 5: Tích hợp CI

CI phải gọi `./mvnw`. Kiểm tra mirror, checksum/provenance, JDK setup và runner sạch. Commit trọn bộ thay đổi Wrapper sau review.

### Bước 6: Chuẩn bị rollback

Rollback thường phải trả lại cả wrapper files và plugin/JDK configuration phù hợp. Không chỉ sửa số version trong distribution URL rồi tin rằng mọi thứ đã giống bản trước.

## 12. Quy trình nâng Gradle Wrapper có kiểm soát

### Bước 1: Chốt baseline

~~~bash
./gradlew --version
./gradlew clean build
~~~

Ghi Gradle JVM, toolchains, plugins, warnings, test results và artifacts.

### Bước 2: Xác minh ma trận tương thích

Kiểm tra bản Gradle target có chạy trên JDK đang dùng cho daemon không, có hỗ trợ toolchain JDK cần thiết không, và plugins có hỗ trợ Gradle mới không.

### Bước 3: Nâng Wrapper

~~~bash
./gradlew wrapper --gradle-version 8.10.2 --distribution-type bin
~~~

Version là minh họa. Theo quy trình của bản Gradle tương ứng, chạy lại wrapper task khi cần để cập nhật đầy đủ wrapper JAR và launcher scripts, không chỉ properties.

### Bước 4: Kiểm tra

~~~bash
./gradlew --version
./gradlew --warning-mode all build
~~~

Cờ `--warning-mode all` (trên các bản Gradle hỗ trợ) giúp hiện các cảnh báo deprecated API; nó không tự thay thế test.

### Bước 5: Review và commit

Rà soát:

~~~text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
~~~

Xác minh nguồn, diff, checksum và các plugin changes. Khi rollback, khôi phục bộ file tương thích với distribution version trước.

## 13. CI phải dùng Wrapper và JDK rõ ràng

Một pipeline tốt ghi rõ JDK, rồi dùng Wrapper của repository.

Ví dụ GitHub Actions cho Maven (chỉ minh họa, action versions phải tuân theo policy tổ chức):

~~~yaml
name: Maven CI

on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven
      - name: Show versions
        run: |
          java -version
          ./mvnw --version
      - name: Verify
        run: ./mvnw -B clean verify
~~~

Ví dụ Gradle:

~~~yaml
name: Gradle CI

on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: gradle
      - name: Show versions
        run: |
          java -version
          ./gradlew --version
      - name: Build
        run: ./gradlew clean build
~~~

Đây là cấu trúc ví dụ; các tổ chức có thể yêu cầu pin actions theo commit SHA, giới hạn token permissions hoặc dùng runner nội bộ.

### 13.1. Các lệnh dễ gây lệch

~~~text
Developer: ./gradlew build  -> Gradle distribution trong repository
CI:        gradle build     -> Gradle cài toàn cục trên runner

Developer: ./mvnw verify   -> Maven distribution trong repository
CI:        mvn verify      -> Maven cài toàn cục trên runner
~~~

Nếu CI dùng công cụ toàn cục, Wrapper không còn đảm bảo cả nhóm dùng chung version. Kiểm tra IDE, Dockerfile, release scripts, scheduled jobs và dependency-update bots, không chỉ workflow YAML chính.

## 14. Bảo mật Wrapper và nguồn tải distribution

Wrapper là một phần của software supply chain, vì launcher/download/bootstrap thực thi mã trước khi build.

### 14.1. Distribution URL

Phải kiểm tra URL được chọn:

- Nguồn chính thức hoặc artifact mirror nội bộ được phê duyệt.
- HTTPS và TLS trust configuration đúng.
- Artifact/version immutable hoặc có chính sách bảo vệ.
- Redirect/proxy không đưa đến domain không mong muốn.
- Có thể audit nguồn, checksum và bản phát hành.

Không tự đổi sang nguồn không tin cậy chỉ để vượt qua lỗi network.

### 14.2. Checksum

Gradle Wrapper hỗ trợ `distributionSha256Sum` trong các phiên bản thích hợp. Maven Wrapper cũng có khả năng validation tuỳ version/cấu hình. Hãy lấy checksum mong đợi từ nguồn tin cậy **độc lập với file vừa tải**.

Nếu chỉ hash một file đã tải từ nguồn không đáng tin rồi lưu hash đó, vẫn chưa chứng minh file có nguồn gốc hợp lệ.

### 14.3. Wrapper scripts và JAR

Wrapper script/JAR có thể chạy với quyền của developer hoặc CI. Cần:

- Review thay đổi scripts.
- Xác minh wrapper JAR của release được chọn.
- Không chạy PR chưa tin cậy với secrets production.
- Phân quyền tối thiểu cho CI token.
- Cân nhắc wrapper validation và dependency verification theo chính sách.
- Không đưa credentials vào `distributionUrl`, source control hoặc logs.

### 14.4. Proxy, mạng nội bộ và offline

CI sạch có thể không tải được distribution nếu phụ thuộc proxy/certificate mà máy developer đã cấu hình. Dự án nên xác định:

- Artifact mirror được phê duyệt.
- Quy trình cung cấp CA/proxy/credentials.
- Checksum và cache policy.
- Khả năng build offline nếu là yêu cầu vận hành.
- Cách phân biệt lỗi tải Wrapper distribution và lỗi tải Maven/Gradle dependencies.

## 15. Dự án đa module và monorepo

### Maven reactor

~~~text
repo/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/...
├── api/pom.xml
├── service/pom.xml
└── integration-tests/pom.xml
~~~

Dùng Wrapper ở root:

~~~bash
./mvnw verify
./mvnw -pl service -am test
~~~

`-pl` chọn project và `-am` thêm các project phụ thuộc trong reactor cần build theo lệnh. Các module có thể dùng Java target khác nhau theo chính sách; Wrapper chung không tự đồng nhất từng compiler configuration.

### Gradle multi-project

~~~text
repo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── app/build.gradle.kts
└── core/build.gradle.kts
~~~

Chạy task theo project:

~~~bash
./gradlew :app:build
./gradlew :core:test
~~~

### Monorepo nhiều build root

Một monorepo có thể có ứng dụng Maven và Gradle độc lập, mỗi thư mục con có Wrapper riêng. CI phải chạy đúng working directory và launcher, không lấy Wrapper ở build root khác.

Nếu tổ chức có mục tiêu chuẩn hóa Maven/Gradle version, cần điều phối nâng version bằng PR và ma trận kiểm thử; không bỏ Wrapper riêng rồi dùng tool toàn cục.

## 16. Build reproducibility cần nhiều thứ hơn Wrapper

Một build có thể dùng cùng Maven/Gradle version mà khác output vì:

- JDK vendor, update hoặc compiler flags khác.
- Plugin versions hoặc transitive dependencies thay đổi.
- SNAPSHOT, version ranges hoặc dynamic versions.
- Locale, timezone, charset và line endings.
- Timestamp chèn vào JAR/manifest hoặc mã được sinh.
- OS/architecture/native libraries.
- Build environment variables hoặc external services.
- Thứ tự file trong archive.
- Test concurrency và dữ liệu môi trường.

Nên ghi trong build metadata:

~~~text
buildTool=Maven/Gradle
buildToolVersion=...
wrapperDistributionUrl=...
jdkVendor=...
jdkVersion=...
compilerToolchain=...
javaReleaseTarget=...
pluginAndDependencyVersions=...
gitCommit=...
artifactSha256=...
~~~

Tuỳ hệ thống, metadata có thể nằm trong CI logs, provenance attestation hoặc SBOM. Không đưa credentials và secrets vào metadata.

## 17. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân cần khảo sát | Bằng chứng |
|---|---|---|
| `./gradlew: Permission denied` | Launcher thiếu executable bit | Git file mode và OS |
| `Could not determine Java version` | Gradle cũ không nhận version JDK mới | Wrapper Gradle và JDK matrix |
| `UnsupportedClassVersionError` | JVM build/plugin quá cũ để đọc classfile | JVM và bytecode version |
| `source option 5 is no longer supported` | Compiler target mặc định quá cũ | Compiler plugin, `--release` |
| `NoClassDefFoundError` trong plugin | Plugin không tương thích hoặc thiếu dependency | Stack trace và plugin graph |
| Lỗi tải distribution | URL, proxy, TLS, checksum, mạng | Wrapper properties và log download |
| Wrapper không tìm thấy bootstrap class | File JAR/script thiếu hoặc lỗi | Các file Wrapper đã commit |
| Maven build được nhưng tests không chạy | Surefire/JUnit provider, plugin hoặc JDK runtime | Test plugin version và logs |
| Gradle daemon lỗi | Gradle JVM hoặc plugin incompatible | `./gradlew --version`, daemon logs |
| Local pass, CI fail | CI dùng tool/JDK khác | CI commands, output `--version` |
| Build khác dù wrapper giống | Dynamic deps, snapshot, env | Lockfile, effective POM, dependency graph |

Khi xử lý lỗi, phân biệt tầng **bootstrap**, **build tool runtime**, **plugin/build logic**, **compiler/toolchain**, **dependency resolution** và **test/deployment runtime**. Một exception không nhất thiết xuất phát từ thay đổi source code.

## 18. Quy trình chẩn đoán khi nâng JDK

1. **Wrapper chạy được?** Kiểm tra `./mvnw --version` hoặc `./gradlew --version`. Nếu thất bại, xem scripts, JAR, URL, network và quyền file.
2. **Build tool dùng JDK nào?** Đọc output version, Java home, CI setup và IDE configuration.
3. **Phiên bản công cụ có hỗ trợ JDK đó?** So ma trận Maven/Gradle và JDK mục tiêu.
4. **Plugins có tương thích?** Xác định plugin có stack trace lỗi, version và API sử dụng.
5. **Compiler target là gì?** Kiểm tra toolchain, `--release`, source/API và classfile version.
6. **Dependency đã được khóa?** So sánh resolved versions, plugin graph và lockfiles.
7. **Test đang chạy trên JDK nào?** Test JVM có thể khác compiler JDK hoặc runtime production.
8. **Artifact deploy dùng runtime nào?** Docker image, installer hoặc runtime image có thể khác CI.
9. **Có thể tái tạo từ checkout sạch?** Chạy theo công cụ và mạng chuẩn của tổ chức.
10. **Có thể rollback?** Khôi phục Wrapper và cấu hình JDK/plugin đi kèm, test artifact baseline.

Không nên đổi đồng loạt JDK, Gradle/Maven, framework và dependencies trong một lần nếu có thể tách thay đổi. Mỗi nhóm thay đổi có thể được kiểm thử và rollback riêng để dễ xác định nguyên nhân.

## 19. Lộ trình nâng Java có Wrapper

Một tiến trình thực tế:

### Giai đoạn A — Chuẩn hóa build hiện tại

- Đưa Wrapper vào Git nếu chưa có.
- Sửa README/CI để dùng Wrapper.
- Cố định các plugin và versions quan trọng.
- Ghi baseline Maven/Gradle/JDK và kết quả test.

### Giai đoạn B — Nâng build tool có kiểm soát

- Chọn bản Maven/Gradle hỗ trợ JDK hiện tại và JDK đích.
- Cập nhật đầy đủ Wrapper files.
- Nâng plugin cần thiết để build xanh với JDK cũ khi khả thi.
- Xác minh CI và source checkout sạch.

### Giai đoạn C — Nâng JDK/toolchain

- Chọn JDK mới rõ vendor/version.
- Giữ `--release` cũ khi cần duy trì runtime compatibility.
- Kiểm tra annotation processors, bytecode tools và plugins.
- Chạy test trên JDK target và runtime tối thiểu.

### Giai đoạn D — Nâng Java source/API target khi cần

- Thay đổi `--release` trong commit riêng.
- Sửa source/dependencies dùng API JDK mới.
- Chạy integration tests và compatibility test theo cam kết.

### Giai đoạn E — Phát hành và bảo trì

- Ghi artifact hash, Wrapper/JDK versions vào release metadata.
- Kiểm tra packaging và launcher production.
- Chuẩn bị rollback theo bản commit đã biết chạy tốt.
- Có lịch nâng Wrapper/plugins theo các bản vá bảo mật và hỗ trợ của vendor.

## 20. Checklist cho Wrapper trong Java migration

- [ ] Đã xác định đúng Maven/Gradle build root của dự án.
- [ ] Đã có scripts và bootstrap files Wrapper tương ứng.
- [ ] Đã commit Wrapper vào Git với executable bit phù hợp.
- [ ] Đã xác minh distribution URL và build tool version.
- [ ] Đã kiểm tra checksum/provenance khi wrapper version hỗ trợ.
- [ ] Đã dùng Wrapper thay vì binary Maven/Gradle toàn cục trong README và CI.
- [ ] Đã ghi JVM thực sự chạy Maven/Gradle.
- [ ] Đã phân biệt build JVM với Java toolchain JDK.
- [ ] Đã cố định source/API/bytecode target theo yêu cầu.
- [ ] Đã đối chiếu phiên bản Maven/Gradle với ma trận JDK.
- [ ] Đã kiểm tra plugin/build logic compatibility.
- [ ] Đã kiểm soát direct và transitive dependency versions.
- [ ] Đã kiểm tra SNAPSHOT/dynamic versions, BOM hoặc lockfiles.
- [ ] Đã chạy build/test trên đúng JDK và OS mục tiêu.
- [ ] Đã kiểm tra khả năng tải distribution ở CI sạch, proxy và mirror.
- [ ] Đã review thay đổi wrapper JAR/scripts như thay đổi mã thực thi.
- [ ] Đã lưu build metadata, artifact hash và kết quả test.
- [ ] Đã có kế hoạch rollback cho Wrapper/JDK/plugin và artifact.

## 21. Kết luận

Maven Wrapper và Gradle Wrapper giúp một repository cố định **phiên bản công cụ build**, giảm sự phụ thuộc vào công cụ toàn cục trên máy developer hoặc runner. Maven thường khai báo distribution trong `.mvn/wrapper/maven-wrapper.properties`; Gradle dùng `gradle/wrapper/gradle-wrapper.properties` cùng wrapper scripts và JAR tương ứng.

Trong Java Advance Compatibility Migration, phải phân biệt **Wrapper distribution version**, **JDK chạy Maven/Gradle**, **compiler toolchain**, **Java release target** và **plugin/dependency versions**. Việc nâng một tầng không tự động nâng các tầng còn lại. Sự nhất quán đòi hỏi cả cấu hình CI, provenance/checksum, dependency management và kiểm thử trên runtime dự kiến.

Quy trình bền vững là dùng Wrapper trong mọi môi trường, chọn bản build tool hỗ trợ JDK mục tiêu, cập nhật trọn bộ wrapper files, review bảo mật, nâng plugins theo bằng chứng và ghi lại metadata của từng bản phát hành. Khi đó Wrapper trở thành một thành phần của hợp đồng tái tạo và bảo trì ứng dụng Java, thay vì chỉ là script khởi chạy tiện lợi.

# Sử dụng Wrapper và cố định môi trường build trên máy chạy CI

## 1. Mục tiêu

Một dự án Java thường chạy được trên máy lập trình nhưng thất bại ở CI vì mỗi môi trường dùng Gradle/Maven/JDK khác nhau. Chẳng hạn developer dùng Gradle 8.8 và JDK 17, còn runner cài Gradle 8.5 và JDK 21; build script, compiler, plugins hoặc test runtime có thể tạo kết quả khác.

**Wrapper** giải quyết việc chọn đúng phiên bản build tool: Gradle Wrapper chạy Gradle distribution được khai báo trong repository; Maven Wrapper chạy Maven distribution được khai báo trong repository. **Cố định môi trường CI** còn phải kiểm soát JDK vendor/major/patch, OS/architecture, plugin/dependency versions, repository inputs, build parameters và những biến môi trường ảnh hưởng kết quả.

Bài học tách thành ba lớp:

1. **Build tool:** Gradle Wrapper hoặc Maven Wrapper pin phiên bản Gradle/Maven và có thể kiểm tra checksum distribution.
2. **Java toolchain:** chọn JDK để chạy build tool, compile source, chạy tests và tạo bytecode mục tiêu.
3. **CI execution environment:** cố định runner/container, architecture, action versions, dependency resolution, environment variables, secrets và cache policy.

~~~text
Source repository
  ├─ gradlew / gradlew.bat
  ├─ gradle/wrapper/gradle-wrapper.properties
  ├─ mvnw / mvnw.cmd
  ├─ .mvn/wrapper/maven-wrapper.properties
  ├─ build.gradle(.kts) / pom.xml
  ├─ dependency locks + verification metadata
  └─ CI workflow
          │
          ▼
CI runner/container đã kiểm soát
  ├─ OS + architecture
  ├─ JDK vendor/version
  ├─ Gradle/Maven Wrapper
  ├─ plugins + dependency inputs
  └─ environment/build parameters
          │
          ▼
clean build + tests + executable Spring Boot JAR
          │
          ▼
artifact checksum / image / release
~~~

Sau bài học, bạn có thể tạo/cập nhật Wrapper đúng cách, xác minh distribution, chạy build qua Wrapper trong CI, khóa Java compiler target, khóa dependency versions, kiểm tra cache và ghi nhận build environment để tái hiện lỗi.

**Phiên bản minh họa:** Spring Boot 3.3.13, Java 17 và Gradle 8.8/Maven 3.9.9. Các phiên bản này tạo thành một bộ ví dụ đào tạo; chúng không phải tuyên bố về bản mới nhất. Khi áp dụng cho repository thực, phải chọn versions tương thích với plugin, dependencies và chính sách cập nhật bảo mật hiện tại.

## 2. Vì sao CI phải dùng Wrapper?

Nếu workflow gọi lệnh:

~~~bash
gradle clean test bootJar
~~~

thì nó dùng Gradle được cài sẵn trên runner hoặc nằm trong PATH. Một runner khác có thể cài version khác. Cùng repository nhưng kết quả build phụ thuộc môi trường bên ngoài source control.

Với Gradle Wrapper:

~~~bash
./gradlew clean test bootJar
~~~

Wrapper đọc `gradle/wrapper/gradle-wrapper.properties`, tải đúng distribution nếu chưa có trong cache và chạy Gradle version được dự án khai báo. Trên Windows:

~~~powershell
.\gradlew.bat clean test bootJar
~~~

Maven cũng tương tự. Thay:

~~~bash
mvn clean verify
~~~

bằng:

~~~bash
./mvnw -B -ntp clean verify
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd -B -ntp clean verify
~~~

**Wrapper không tự cố định toàn bộ môi trường:** nó pin build tool distribution, không tự pin JDK patch, OS, CPU architecture, Maven/Gradle plugins, dependencies hoặc CI actions. Vì vậy Wrapper là nền tảng đầu tiên của build repeatability, không phải giải pháp duy nhất.

### 2.1. Những file Wrapper cần được commit

| Công cụ | Files thường cần trong repository | Vai trò |
| --- | --- | --- |
| Gradle | `gradlew`, `gradlew.bat` | Script khởi chạy |
| Gradle | `gradle/wrapper/gradle-wrapper.jar` | Wrapper bootstrap code |
| Gradle | `gradle/wrapper/gradle-wrapper.properties` | Distribution URL/checksum |
| Maven | `mvnw`, `mvnw.cmd` | Script khởi chạy |
| Maven | `.mvn/wrapper/maven-wrapper.properties` | Maven distribution/wrapper configuration |
| Maven | Wrapper JAR nếu wrapper type dùng JAR | Bootstrap code |

Cấu trúc chính xác Maven Wrapper phụ thuộc wrapper type/version. Nếu dùng kiểu `only-script`, tập file có thể khác kiểu dùng wrapper JAR. Commit **đầy đủ những file được loại wrapper đang cấu hình yêu cầu**; đừng xóa wrapper JAR chỉ vì một project khác dùng only-script.

Không sinh lại wrapper trong mỗi CI job. CI phải dùng đúng wrapper đã review và commit cùng source code. Việc nâng Gradle/Maven Wrapper nên là một thay đổi có review, test và cập nhật checksums.

## 3. Gradle Wrapper: cấu hình và xác minh distribution

### 3.1. Tạo hoặc nâng Wrapper

Nếu máy có Gradle cài sẵn, từ root project chạy:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Lệnh tạo/cập nhật wrapper files để sử dụng Gradle 8.8 binary distribution. Nếu project chưa có wrapper, cần Gradle local phù hợp để khởi tạo lần đầu; sau đó CI chỉ gọi `./gradlew`.

Có thể truyền checksum của distribution trong lúc tạo wrapper (nếu task/Gradle version hỗ trợ option tương ứng):

~~~bash
gradle wrapper \
  --gradle-version 8.8 \
  --distribution-type bin \
  --gradle-distribution-sha256-sum "$GRADLE_DIST_SHA256"
~~~

`GRADLE_DIST_SHA256` phải chứa SHA-256 **chính thức** của đúng file `gradle-8.8-bin.zip`, lấy từ trang checksum của Gradle qua kênh tin cậy. Không lấy checksum từ một mirror không xác minh hoặc tự điền chuỗi giả.

### 3.2. Nội dung gradle-wrapper.properties

Ví dụ file `gradle/wrapper/gradle-wrapper.properties`:

~~~properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.8-bin.zip
distributionSha256Sum=OFFICIAL_SHA256_FOR_EXACT_GRADLE_8_8_BIN_ZIP
networkTimeout=10000
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
~~~

Trong file thật, thay giá trị `distributionSha256Sum` bằng checksum 64 ký tự hex chính thức. Dòng minh họa chữ hoa là mô tả vị trí cần đặt giá trị, **không phải checksum hợp lệ để commit**. Bài học không bịa checksum cho distribution.

- `distributionUrl` xác định file Gradle distribution tải về. Dùng HTTPS và version cố định.
- `distributionSha256Sum` khiến Wrapper xác minh distribution ZIP sau khi tải; nếu checksum không khớp, việc sử dụng distribution bị từ chối.
- `networkTimeout` đặt timeout tải distribution theo milliseconds.
- `distributionType=bin` trong lệnh tạo wrapper chọn binary distribution gọn hơn `all`; `all` thường bao gồm sources/docs, hữu ích khi cần IDE source attachments nhưng không cần cho build CI thông thường.

Không dùng URL dạng `gradle-8.+-bin.zip` hoặc `latest` cho release build; version động làm build tool thay đổi ngoài ý muốn.

### 3.3. Xác minh Wrapper đang chạy đúng version

~~~bash
./gradlew --version
~~~

Output phải cho biết Gradle 8.8 theo ví dụ và thông tin JVM đang chạy Gradle. Java version có thể khác compile toolchain nếu project cấu hình Gradle toolchains.

Để xem JDK toolchains mà Gradle phát hiện:

~~~bash
./gradlew javaToolchains
~~~

Task này hữu ích khi Java plugin được áp dụng. Nó cho biết JDK candidates/toolchains Gradle có thể dùng, không chứng minh container runtime production dùng cùng JVM.

### 3.4. Kiểm tra Wrapper JAR

`gradle-wrapper.jar` là executable bootstrap code, vì vậy phải xem nó như một thành phần cần kiểm soát. Dùng Gradle Wrapper Validation Action trong CI hoặc quy trình validation tương đương để phát hiện wrapper JAR không hợp lệ/đã bị thay đổi.

Ví dụ GitHub Actions step (major version minh họa):

~~~yaml
- name: Validate Gradle Wrapper
  uses: gradle/actions/wrapper-validation@v4
~~~

Với workflow có yêu cầu supply-chain cao, pin action bằng **full commit SHA đã được review**, không chỉ tag mutable. Đọc tài liệu action để chọn phiên bản đang được tổ chức phê duyệt.

### 3.5. Cập nhật Wrapper có kiểm soát

Khi nâng Gradle:

1. Kiểm Gradle compatibility matrix với JDK, Spring Boot plugin, Kotlin plugin và các plugins khác.
2. Chạy lệnh wrapper bằng Gradle local phù hợp.
3. Ghi checksum chính thức cho đúng distribution.
4. Review diff của cả properties, scripts và wrapper JAR.
5. Chạy `./gradlew --version` để xác nhận.
6. Chạy clean build/tests trên JDK CI mục tiêu.
7. Commit wrapper update cùng release note/PR giải thích version change.

Không chỉ sửa một con số trong properties mà quên wrapper bootstrap JAR/scripts nếu dự án cần cập nhật chúng theo phiên bản Wrapper mới.

## 4. Maven Wrapper: pin Maven distribution

### 4.1. Tạo Maven Wrapper

Nếu máy đã có Maven cài sẵn, từ root project có thể tạo wrapper bằng Maven Wrapper Plugin. Ví dụ dùng plugin version được pin:

~~~bash
mvn org.apache.maven.plugins:maven-wrapper-plugin:3.3.2:wrapper -Dmaven=3.9.9
~~~

Lệnh tạo các wrapper files cho Maven 3.9.9 theo wrapper type/configuration. Sau khi tạo, commit wrapper scripts và thư mục `.mvn/wrapper` cùng source.

Tên plugin version 3.3.2 và Maven 3.9.9 là mốc minh họa. Khi nâng, kiểm plugin compatibility và chọn version được tổ chức duyệt. Không để CI tự chạy `mvn wrapper:wrapper` rồi tạo wrapper mới tùy runner.

### 4.2. maven-wrapper.properties

Ví dụ `.mvn/wrapper/maven-wrapper.properties`:

~~~properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
distributionSha256Sum=OFFICIAL_SHA256_FOR_EXACT_MAVEN_3_9_9_BIN_ZIP
wrapperVersion=3.3.2
~~~

Dòng checksum phải được thay bằng SHA-256 chính thức của đúng Maven distribution. Tên và các thuộc tính hỗ trợ phụ thuộc Maven Wrapper version/type; một số cấu hình wrapper JAR còn có thể dùng `wrapperUrl`/`wrapperSha256Sum`. Kiểm file được plugin sinh ra và tài liệu đúng version trước khi bổ sung thuộc tính; đừng tự thêm key không được wrapper hỗ trợ rồi cho rằng checksum đang được kiểm.

- `distributionUrl` pin Maven version và distribution type.
- `distributionSha256Sum` xác minh archive Maven tải về khi wrapper version hỗ trợ.
- `wrapperVersion` ghi wrapper implementation version; không thay thế kiểm tra integrity wrapper bootstrap code.

### 4.3. Chạy Maven qua Wrapper

~~~bash
./mvnw --version
./mvnw -B -ntp -C clean verify
~~~

Ý nghĩa flags:

- `-B`: batch mode, phù hợp CI không tương tác.
- `-ntp`: tắt transfer progress để log ngắn/gọn hơn.
- `-C`: strict checksum mode khi Maven tải artifacts; checksum lỗi sẽ được xử lý nghiêm ngặt theo Maven Resolver behavior.

Trên Windows:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd -B -ntp -C clean verify
~~~

`-C` chỉ là một lớp kiểm tra checksum khi resolve artifacts từ repository; không ký JAR phát hành, không thay xác minh identity của repository và không đảm bảo repository không thể cung cấp cả artifact lẫn checksum bị thay thế.

### 4.4. Wrapper type và wrapper bootstrap

Maven Wrapper có thể dùng script-only hoặc bootstrap JAR tùy cấu hình. Không xóa `maven-wrapper.jar` nếu script đang cần nó; ngược lại không commit JAR dư nếu project dùng loại wrapper không cần JAR. Wrapper plugin có thể tạo cấu trúc khác nhau giữa các mode.

Trong production, xác minh wrapper bootstrap files bằng cơ chế được tổ chức chấp thuận, giữ HTTPS, checksum distribution và review mọi thay đổi wrapper. Đừng chạy wrapper script lấy từ một pull request không tin cậy với credentials có quyền publish release.

## 5. Wrapper không pin JDK: cố định Java toolchain

Gradle Wrapper pin Gradle, Maven Wrapper pin Maven. Cả hai **không tự pin Java runtime/compiler**. Một runner có thể chạy Gradle 8.8 bằng JDK 21 nhưng project yêu cầu compile Java 17.

### 5.1. Gradle Java toolchain và release target

Groovy DSL:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Kotlin DSL:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
        vendor.set(JvmVendorSpec.ADOPTIUM)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Toolchain yêu cầu JDK 17 của vendor đã chọn cho Java tasks; `options.release=17` ràng buộc source/API/bytecode về Java 17. `vendor` là lựa chọn tùy theo project; nếu tổ chức chuẩn hóa Temurin/Adoptium, khai báo rõ giúp tránh dùng JDK khác vendor mà không nhận ra.

Toolchain có thể được Gradle auto-detect hoặc auto-provision theo resolver/configuration của project. Để build CI có thể tái hiện, runner nên cài đúng JDK trước hoặc cấu hình provisioning từ repository được tin cậy; không giả định Gradle tự tải JDK trong mọi môi trường.

### 5.2. Gradle daemon JVM khác compiler toolchain

`./gradlew --version` cho biết JVM chạy Gradle. `java.toolchain` chọn JDK cho compile/test tasks được cấu hình. Có thể dùng JDK 21 để chạy Gradle nhưng JDK 17 để compile, nếu Gradle version và plugins hỗ trợ cấu hình đó.

Tuy nhiên, để đơn giản hóa và giảm biến động CI, ví dụ thực hành nên dùng JDK 17 cho cả runner và Java toolchain. Nếu chủ đích tách hai version, ghi rõ và test compatibility.

### 5.3. Maven compiler release

Trong POM Spring Boot 3.3.13:

~~~xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

`maven.compiler.release` cấu hình Maven Compiler Plugin tạo bytecode và API target Java 17 khi plugin version hỗ trợ thuộc tính này. Nó **không cài JDK 17**. Nếu Maven process chạy trên JDK 11, compiler không thể dùng `--release 17`; cần provision JDK build phù hợp hoặc cấu hình Maven Toolchains Plugin để chọn JDK 17.

### 5.4. Kiểm tra JDK trên CI

~~~bash
java -version
javac -version
./gradlew --version
./gradlew javaToolchains
~~~

Với Maven:

~~~bash
java -version
javac -version
./mvnw --version
~~~

Ghi lại vendor, full patch version, architecture và đường dẫn JDK trong CI log. `java -version` chỉ xác nhận executable trên PATH; nếu Gradle toolchain chọn một JDK khác, phải kiểm tra toolchain output và task configuration nữa.

## 6. Cố định dependencies và plugins

Một Wrapper chính xác vẫn có thể cho kết quả khác nếu dependency versions thay đổi, repository trả artifact khác hoặc plugin version được khai báo động.

### 6.1. Gradle dependency locking

Gradle dependency locking giúp cố định resolved versions. Có thể bật cho mọi configurations:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Hoặc Kotlin DSL:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Sau đó resolve các configurations cần thiết và ghi lock state:

~~~bash
./gradlew dependencies --write-locks
~~~

Kiểm tra các file lock được tạo (thường dưới `gradle/dependency-locks` hoặc vị trí theo cấu hình Gradle) rồi commit. Khi dependency version thay đổi có chủ đích, update lockfiles và review diff.

Không phải mọi plugin/metadata dynamic đều tự được khóa chỉ bằng một file lock duy nhất. Kiểm cấu hình resolution strategy, included builds, plugin management và dependency substitution nếu project có.

### 6.2. Gradle dependency verification

Gradle hỗ trợ checksum/signature verification cho dependencies/plugins thông qua:

~~~text
gradle/verification-metadata.xml
~~~

Tạo baseline ban đầu:

~~~bash
./gradlew --write-verification-metadata sha256
~~~

Nếu muốn thu thập thêm PGP signature metadata (khi repositories cung cấp chữ ký phù hợp):

~~~bash
./gradlew --write-verification-metadata sha256,pgp
~~~

**Review file được tạo trước khi commit.** Baseline tự sinh từ repository đang resolve không chứng minh repository ban đầu đáng tin; đối chiếu checksum/key của những dependency quan trọng từ nguồn độc lập. Verification metadata bảo vệ inputs được Gradle resolve, không tự ký output JAR do project tạo.

### 6.3. Pin plugin versions

Gradle plugins nên có version rõ ràng trong `plugins` block hoặc plugin management:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}
~~~

Không dùng dynamic plugin versions hoặc logic lấy `latest` từ Internet trong release build. Với version catalogs, commit `gradle/libs.versions.toml` và review update.

### 6.4. Maven dependencies/plugins

Maven nên pin Spring Boot parent/BOM version, các plugin version do parent quản lý hoặc được khai báo trong `pluginManagement`. Tránh dependency version ranges, `LATEST`, `RELEASE` và SNAPSHOT trong release builds trừ khi có policy riêng.

Maven Enforcer Plugin có thể kiểm tra Maven/JDK requirements, dependency convergence hoặc cấm SNAPSHOT. Nếu dùng plugin này, pin plugin version trong POM/parent và review rules; đừng dùng rule mơ hồ khiến CI và developer khác nhau.

Maven strict checksum mode `-C` giúp phát hiện checksum mismatch từ repository, nhưng **không thay** SBOM, lock/verification policy hoặc trust vào repository manager.

## 7. Cố định CI runner và execution environment

Để build có thể tái hiện, ghi rõ ít nhất:

| Đầu vào | Cần cố định/ghi nhận | Vì sao quan trọng |
| --- | --- | --- |
| OS image | Distro/release hoặc container digest | Toolchain, libc, certificates và filesystem |
| CPU architecture | amd64/arm64 | Native dependencies và compiler behavior |
| JDK | Vendor, major và patch | Compiler/JVM APIs, bugs và security patches |
| Gradle/Maven | Wrapper distribution + checksum | Build engine version |
| Plugins | Exact plugin versions | Task graph, compiler/package behavior |
| Dependencies | Locking, verification, BOM | Tránh version drift |
| Repository | Approved mirrors, TLS/trust config | Source of dependencies |
| Environment | Locale, timezone, encoding, variables | Timestamp/format/conditional logic |
| Build parameters | Tasks, profiles, flags, properties | Cùng source nhưng command khác có thể cho output khác |
| CI actions/plugins | Version hoặc immutable commit SHA | Tránh action code thay đổi ngoài PR |
| Secrets | Runtime injection từ secret manager | Không đưa credentials vào source/log/artifact |
| Cache | Key, trust boundary, lifecycle | Tăng tốc nhưng không làm thay đổi correctness |

### 7.1. JDK major và patch

Cấu hình `java-version: '17'` trong một CI setup action thường chọn bản JDK mới nhất phù hợp dòng 17 mà action tìm được tại thời điểm chạy. Đây là cách giữ security patch updates tự động, nhưng **không phải pin patch tuyệt đối**.

Nếu yêu cầu build bytes có thể tái lập ở mức cao, pin vendor + full JDK patch/build và runner/container digest. Đồng thời phải có lịch cập nhật security patch; pin cứng không được trở thành lý do giữ một JDK có lỗ hổng đã biết.

### 7.2. Runner labels có thể mutable

Ví dụ `ubuntu-24.04` giúp cố định OS release family hơn `ubuntu-latest`, nhưng image runner hosted vẫn được cập nhật theo thời gian. Nếu cần tái hiện nghiêm ngặt, dùng approved build container image theo digest trên runner phù hợp hoặc self-hosted runner được quản lý, ghi OS/architecture/toolchain metadata.

Không dùng digest giả. Lấy digest thực từ registry được tổ chức phê duyệt và cập nhật qua PR có review.

### 7.3. Locale, timezone và encoding

Một số build scripts hoặc code generators có thể phụ thuộc locale/timezone/default charset. CI nên đặt những giá trị cần thiết rõ ràng, ví dụ:

~~~bash
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export TZ=UTC
~~~

Đây là ví dụ trên Linux runner; không phải biến có cùng semantics trên mọi OS. Java 17 mặc định dùng UTF-8 trên nhiều môi trường hiện đại nhưng không nên dựa vào default hệ điều hành cho các công cụ khác. Nếu output cần timestamp, dùng UTC/Instant và định nghĩa nguồn timestamp; tránh lấy `now` tùy ý trong artifact khi mục tiêu là reproducible build.

### 7.4. Ghi lại môi trường build

Có thể xuất các thông tin sau vào CI log:

~~~bash
uname -a
uname -m
java -version
javac -version
./gradlew --version
./gradlew javaToolchains
~~~

Maven job thay hai lệnh cuối bằng:

~~~bash
./mvnw --version
~~~

Không dump toàn bộ environment bằng `env` hoặc `printenv` trong CI public logs; có thể lộ tokens, passwords và secrets. Chỉ in allowlist những biến không nhạy cảm cần chẩn đoán.

## 8. Ví dụ GitHub Actions: Gradle Wrapper + Java 17

Workflow minh họa tại `.github/workflows/gradle-ci.yml`:

~~~yaml
name: Gradle CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-24.04

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Validate Gradle Wrapper
        uses: gradle/actions/wrapper-validation@v4

      - name: Set up JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Show build environment
        run: |
          java -version
          javac -version
          ./gradlew --version
          ./gradlew javaToolchains

      - name: Build and test with Wrapper
        run: ./gradlew --no-daemon clean check bootJar
~~~

Đây là workflow minh họa dễ đọc. Trong pipeline production:

- Pin các GitHub Actions bằng full commit SHA đã review (có thể kèm comment version), không chỉ tag như `@v4`.
- Chọn runner image/container theo policy; `ubuntu-24.04` vẫn được hosted runner cập nhật.
- Nếu cần exact JDK patch, đặt full version/build phù hợp và kiểm output sau setup.
- Thêm cache theo key dựa vào Wrapper, JDK, OS và dependency metadata; cache chỉ tối ưu tốc độ.
- Nếu job có quyền publish/sign, tách quyền khỏi pull request từ fork; chỉ release workflow được cấp OIDC/signing permissions.
- Giữ `permissions` tối thiểu, không cấp `contents: write` cho build/test thông thường.

### 8.1. Cache Gradle trong CI

Có thể dùng setup action cache Gradle hoặc cache action riêng. Key nên phụ thuộc ít nhất vào OS, JDK và files quyết định Gradle/dependency graph như:

~~~text
gradle-wrapper.properties
settings.gradle(.kts)
build.gradle(.kts)
gradle/libs.versions.toml
gradle/verification-metadata.xml
gradle/dependency-locks/**
~~~

Không dùng một cache dùng chung không phân biệt branch/trust boundary cho các build không tin cậy và release có quyền publish. Không cache credentials hoặc secret files. Nếu cache bị xóa, build vẫn phải thành công bằng cách tải lại dependencies từ nguồn hợp lệ.

### 8.2. Vì sao dùng `--no-daemon`?

Trong CI, `--no-daemon` giảm phụ thuộc vào Gradle daemon process sống lâu giữa jobs. Gradle có thể vẫn tạo single-use daemon để đáp ứng JVM arguments; flag này không có nghĩa mọi execution luôn là một process đơn giản. Nó hữu ích cho job isolation nhưng không thay Wrapper/JDK pinning.

## 9. Ví dụ GitHub Actions: Maven Wrapper + Java 17

Workflow minh họa tại `.github/workflows/maven-ci.yml`:

~~~yaml
name: Maven CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-24.04

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Show build environment
        run: |
          java -version
          javac -version
          ./mvnw --version

      - name: Build and verify with Maven Wrapper
        run: ./mvnw -B -ntp -C clean verify
~~~

Tương tự Gradle, hãy pin actions bằng full commit SHA và kiểm runner image. `cache: maven` chỉ cache repository artifacts để build nhanh hơn; Maven vẫn phải kiểm checksum/repository policy và build phải chạy được khi cache miss.

Maven Wrapper distribution checksum được kiểm tra theo `maven-wrapper.properties` nếu wrapper version hỗ trợ thuộc tính đó. CI không cần cài Maven global. Nếu gọi `mvn` thay `./mvnw`, bạn đã bỏ qua Maven version pin trong repository.

### 9.1. CI cần chạy trên Windows?

Nếu dự án hỗ trợ Windows, có thể thêm job riêng:

~~~yaml
jobs:
  windows-verify:
    runs-on: windows-2022
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - name: Verify with Maven Wrapper
        shell: pwsh
        run: .\mvnw.cmd -B -ntp -C clean verify
~~~

Tên runner/action version là ví dụ; hãy pin action immutable SHA và runner policy phù hợp. Không chỉ thay path script mà bỏ kiểm thử path separator, file permissions, case sensitivity và native libraries nếu project tuyên bố hỗ trợ Windows.

## 10. Dùng container build environment để giảm biến động runner

Một cách khác là chạy build trong CI container image đã được kiểm soát. Ví dụ cấu trúc workflow (image reference phải được thay bằng digest thật do tổ chức phê duyệt):

~~~yaml
jobs:
  verify:
    runs-on: ubuntu-24.04
    container:
      image: registry.example.org/ci/java17-gradle@sha256:APPROVED_IMAGE_DIGEST

    steps:
      - uses: actions/checkout@v4
      - name: Verify
        run: ./gradlew --no-daemon clean check bootJar
~~~

`registry.example.org` và `APPROVED_IMAGE_DIGEST` chỉ mô tả dạng cấu hình; không phải image/digest có thể dùng ngay. Image CI nên có JDK vendor/patch, OS libraries, certificates và tools được quản lý. Wrapper vẫn được dùng để chọn Gradle/Maven distribution chính xác.

Pin container digest giúp ổn định image layers, nhưng chưa đủ nếu build còn truy cập dependencies động, Maven snapshots, Gradle dynamic versions, remote scripts hoặc external services. Hãy pin và kiểm soát tất cả inputs liên quan.

### 10.1. Không cần nhúng Gradle/Maven global vào image

Có thể tạo CI image chứa JDK và một số tiện ích; project vẫn chạy `./gradlew`/`./mvnw`. Điều này giữ version build tool được xác định bởi repository. Nếu cài global Gradle/Maven trong image chỉ để tạo wrapper, CI lại dễ dùng nhầm global version.

### 10.2. Multi-architecture

Nếu runner chuyển từ amd64 sang arm64, native dependencies, JDK build, test results hoặc OCI image architecture có thể khác. Ghi architecture, chạy tests trên từng platform được hỗ trợ và không chia sẻ native build outputs cache giữa architectures không tương thích.

## 11. Cố định dependency và build plugins trong release

### 11.1. Gradle version catalogs

Dùng `gradle/libs.versions.toml` để tập trung plugin/dependency versions:

~~~toml
[versions]
spring-boot = "3.3.13"
dependency-management = "1.1.7"

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "spring-boot" }
dependency-management = { id = "io.spring.dependency-management", version.ref = "dependency-management" }
~~~

Build script dùng alias đã khai báo. Version catalog giúp review/update tập trung, nhưng không tự khóa mọi transitive versions nếu dependency constraints/BOM không kiểm soát chúng. Kết hợp dependency locking và verification.

### 11.2. Maven BOM và plugin management

Spring Boot parent/BOM giúp quản lý compatible dependency versions. Parent version phải pin cụ thể; plugin versions không do parent quản lý cần được pin trong `pluginManagement` hoặc `build/plugins`.

Không dùng version ranges hoặc `LATEST` trong release build. Tránh SNAPSHOT trong production release trừ khi tổ chức có một quy trình immutable snapshot repository riêng.

### 11.3. Repository mirror

CI nên resolve artifacts từ approved repository manager/mirror với TLS/trust configuration rõ ràng. Không tải dependency/plugin bằng script tùy ý từ URL không review. Nếu dùng credentials, cấp qua secret manager và chỉ cho job cần thiết; không ghi credentials vào `settings.xml` commit trong repository.

### 11.4. Maven Enforcer và Java/Maven requirements

Maven Enforcer Plugin có thể kiểm Maven version/JDK range, dependency convergence và ban snapshots. Ví dụ rule version pin phải nằm trong POM/parent có review. Không dùng một range Java quá rộng rồi tin rằng build luôn cho output giống nhau; nếu mục tiêu Java 17, compiler release và runtime JDK phải được định nghĩa rõ.

## 12. Cache: tối ưu tốc độ, không phải đầu vào tin cậy

CI thường cache:

- Gradle Wrapper distribution và dependency cache.
- Gradle build cache/task outputs nếu được bật.
- Maven local repository `~/.m2/repository`.
- Build outputs trong một số pipeline có điều kiện.

Cache có thể bị eviction, corrupt, stale hoặc đến từ một branch/job khác. Build phải **đúng khi cache rỗng** và cache không được xem là nguồn sự thật duy nhất.

### 12.1. Cache key

Key nên phụ thuộc vào:

- OS/architecture.
- JDK vendor/version.
- Wrapper properties và Gradle/Maven version.
- Dependency lockfiles/verification metadata.
- Build scripts/plugin versions.
- Những build parameters ảnh hưởng outputs.

Nếu cache key không chứa các yếu tố này, job có thể khôi phục cache không tương thích hoặc che giấu thay đổi input.

### 12.2. Cache không thay checksum/verification

Gradle dependency verification, Maven strict checksum mode và repository trust policy vẫn cần hoạt động dù dependencies đã cache. Cache local không tự chứng minh artifact đến từ đúng publisher.

### 12.3. Cache và pull request không tin cậy

Không để một pull request không tin cậy ghi vào cache dùng cho release job có quyền ký/publish nếu cache đó có thể ảnh hưởng build outputs. Phân tách key, branch scope và permissions. Không cache secret material hoặc private signing keys.

### 12.4. Không chạy clean một cách máy móc rồi mong cache mất

`./gradlew clean` dọn build outputs trong workspace; không xóa Wrapper distribution/dependency caches. `mvn clean` xóa target outputs; không xóa toàn bộ Maven local repository. Khi điều tra cache, xác định đúng tầng: wrapper distribution, dependency cache, task/build cache hay workspace outputs.

## 13. Một Java 17 probe để ghi lại môi trường CI

Tạo `BuildEnvironmentProbe.java` để in các thuộc tính không bí mật cần chẩn đoán:

~~~java
public final class BuildEnvironmentProbe {

    public static void main(String[] args) {
        System.out.println("java.version=" +
                System.getProperty("java.version"));
        System.out.println("java.vendor=" +
                System.getProperty("java.vendor"));
        System.out.println("java.vm.name=" +
                System.getProperty("java.vm.name"));
        System.out.println("os.name=" +
                System.getProperty("os.name"));
        System.out.println("os.arch=" +
                System.getProperty("os.arch"));
        System.out.println("file.encoding=" +
                System.getProperty("file.encoding"));
        System.out.println("user.timezone=" +
                System.getProperty("user.timezone"));
    }
}
~~~

Biên dịch/chạy bằng JDK 17:

~~~bash
javac --release 17 BuildEnvironmentProbe.java
java BuildEnvironmentProbe
~~~

Output phụ thuộc JDK vendor/patch, OS, architecture và runtime properties. Không có một stdout cố định áp dụng cho mọi CI runner. Đây là **Java SE program độc lập**, không cần Spring Boot. Nó chỉ ghi lại JVM/runtime properties của process đang chạy probe; không thể tự nhận diện tất cả thông tin CI action, container digest hoặc source commit.

Có thể thêm CI variables đã được allowlist như commit SHA, build run ID và image digest, nhưng không in toàn bộ environment vì có thể lộ secrets.

## 14. Kiểm tra wrapper và build tool khi CI fail

### 14.1. Gradle diagnostics

~~~bash
./gradlew --version
./gradlew javaToolchains
./gradlew tasks --all
./gradlew --no-daemon clean check bootJar --info
~~~

Xem:

- Gradle version có đúng Wrapper properties?
- JVM chạy Gradle có đáp ứng yêu cầu của Gradle/plugin?
- Toolchain Java 17 có được phát hiện/provision?
- Task graph có đúng module/application không?
- Dependency resolution có dùng repository/mirror dự kiến?
- Cache hit/miss có gây sai lệch hoặc chỉ thay đổi thời gian?

### 14.2. Maven diagnostics

~~~bash
./mvnw --version
./mvnw -B -ntp -C help:effective-pom
./mvnw -B -ntp -C clean verify
~~~

Effective POM giúp xem parent/plugin management và compiler config sau khi kế thừa. Nếu toolchain plugin được dùng, kiểm file toolchains trên CI và JDK path tương ứng; không commit absolute path máy developer vào repository.

### 14.3. Kiểm class output khi cần

Gradle:

~~~bash
javap -verbose -classpath build/classes/java/main com.example.Application
~~~

Maven:

~~~bash
javap -verbose -classpath target/classes com.example.Application
~~~

Thay `com.example.Application` bằng fully qualified class thực tế. Nếu target Java 17, main class thường có `major version: 61`. Kiểm class output giúp phân biệt compiler mismatch với Wrapper/runtime issue.

### 14.4. Ghi log mà không làm lộ secrets

Có thể in `java -version`, Wrapper version, OS, architecture, commit SHA và selected tasks. Không in `env`, Maven settings chứa credentials, Gradle properties có tokens hoặc toàn bộ build scan links có thể truy cập private data nếu policy không cho phép.

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `gradlew: command not found` | Wrapper script không commit hoặc chạy sai thư mục | Kiểm root path và `gradlew`; dùng `./gradlew` |
| Windows không chạy `./gradlew` | Dùng sai script | Dùng `.\gradlew.bat` |
| Wrapper tải Gradle thất bại | distribution URL sai, TLS/proxy hoặc checksum mismatch | Kiểm URL/checksum chính thức và network |
| Maven Wrapper không chạy | Thiếu script/properties/bootstrap files | Kiểm wrapper type và commit đủ file |
| Maven Wrapper tải archive nhưng checksum fail | SHA sai hoặc file bị thay đổi | Dừng build, xác minh distribution qua nguồn tin cậy |
| Gradle/Maven version khác local | CI gọi global command thay Wrapper | Đổi thành `./gradlew`/`./mvnw` |
| Java version khác mong đợi | Runner JDK hoặc toolchain khác | Kiểm `java -version`, `--version` và toolchain |
| Java 17 source nhưng class major 65 | Compiler target không được khóa | Dùng `options.release=17`/`maven.compiler.release=17` |
| Plugin resolution khác nhau | Plugin version động hoặc repositories khác | Pin plugin versions và repository policy |
| Dependency version trôi | Dynamic/range/SNAPSHOT hoặc thiếu lock | Dependency locking/BOM/ban snapshots |
| Gradle verification fail | Dependency checksum/signature thay đổi | Điều tra repository/source, review metadata trước update |
| Maven strict checksum fail | Artifact/checksum không khớp | Dừng release và kiểm repository/mirror |
| Build chỉ fail khi cache trống | Phụ thuộc cache ngoài ý muốn hoặc offline input thiếu | Đảm bảo dependency resolution tái lập từ repository |
| CI cache restore gây lỗi lạ | Cache key thiếu OS/JDK/wrapper/lockfile | Điều chỉnh key và phân tách trust boundary |
| Local pass, CI fail trên Linux | File permission/case sensitivity/line endings | Kiểm wrapper executable bit, path case và checkout |
| Local pass, CI fail trên ARM | Native dependency/architecture khác | Test đúng architecture, không dùng cache native chéo |
| Build outputs khác theo timezone | Task/script phụ thuộc clock/locale | Chuẩn hóa UTC/locale, kiểm generated timestamps |
| Action code thay đổi ngoài PR | Dùng tag action mutable | Pin full commit SHA, update có review |
| CI release có secret trong logs | In toàn bộ env/verbose command | Allowlist diagnostics, redact secrets |
| Maven chạy JDK 11 dù setup Java 17 | JAVA_HOME/PATH/toolchain config chưa cập nhật | Kiểm thứ tự setup và `mvnw --version` |
| Wrapper validation fail | Wrapper JAR không được tin cậy/không đúng generated version | Tạo lại từ distribution tin cậy, review binary diff |

### 15.1. Trình tự điều tra

1. Xác nhận job chạy ở repository root và gọi đúng Wrapper script.
2. In Wrapper version và JVM thực thi build tool.
3. Kiểm JDK toolchain/compiler release.
4. Kiểm wrapper distribution URL/checksum và wrapper bootstrap files.
5. Kiểm plugin/dependency locks/verification metadata.
6. Tạm chạy không cache để xác định cache có liên quan; không xóa mọi caches khi chưa biết tầng lỗi.
7. Kiểm OS/architecture/locale/timezone và environment parameters.
8. So sánh build logs/outputs với local theo cùng inputs.
9. Chỉ sau khi build tái hiện ổn định mới publish/sign artifact.

## 16. Bài tập thực hành có đáp án

### Bài 1 — Global Gradle hay Wrapper?

CI đang chạy `gradle clean build` và runner vừa được nâng Gradle. Sửa tối thiểu thế nào?

**Đáp án:** gọi `./gradlew clean build` (Windows dùng `gradlew.bat`) và commit đầy đủ Gradle wrapper files với distribution URL/version/checksum.

### Bài 2 — Wrapper đã pin Gradle, nhưng Java sai

`./gradlew --version` cho thấy Gradle 8.8 nhưng JVM 21. Project cần compile Java 17. Sửa ở đâu?

**Đáp án:** cố định JDK runner/toolchain Java 17; trong Gradle dùng `java.toolchain.languageVersion=17` và `options.release=17`. Wrapper không tự chọn compiler JDK.

### Bài 3 — Checksum Gradle distribution

Một runner tải Gradle distribution từ URL HTTPS, nhưng checksum không khớp. Có nên xóa `distributionSha256Sum` để build tiếp?

**Đáp án:** không. Dừng job, xác minh URL/archive/checksum từ nguồn Gradle tin cậy, kiểm mirror/proxy và chỉ cập nhật checksum sau review.

### Bài 4 — Maven strict checksum

CI chạy `./mvnw -B -ntp -C verify` và Maven báo checksum mismatch của dependency.

**Đáp án:** không chuyển sang `-c`/bỏ strict mode để release. Kiểm artifact/checksum từ repository manager và source, điều tra cache/proxy trước khi tiếp tục.

### Bài 5 — Wrapper update

Một PR đổi Gradle từ 8.8 lên version khác. Những gì cần review?

**Đáp án:** distribution URL/checksum, wrapper scripts/JAR, Gradle/JDK/plugin compatibility, dependency resolution và full clean build/test trên runner mục tiêu.

### Bài 6 — Cache

Build pass khi cache có sẵn, fail khi cache trống vì dependency không resolve.

**Đáp án:** pipeline đang phụ thuộc cache thay vì repository hợp lệ. Kiểm repository/proxy/offline flags, bảo đảm build có thể resolve dependencies khi cache miss.

### Bài 7 — JDK patch

Workflow dùng `java-version: '17'`. Có thể khẳng định luôn dùng cùng patch JDK qua mọi tháng?

**Đáp án:** không. Nó thường chọn bản phù hợp dòng 17 tại thời điểm chạy. Nếu cần pin patch, khai báo full version/build và cố định runner/container; vẫn phải cập nhật security patch có kiểm soát.

### Bài 8 — Action tag

Workflow dùng `actions/checkout@v4`. Có phải action code bất biến tuyệt đối?

**Đáp án:** tag không phải immutable reference tuyệt đối. Với supply-chain policy nghiêm ngặt, pin full commit SHA đã review và cập nhật bằng PR.

### Bài 9 — Toolchain khác Gradle daemon

Gradle daemon chạy JDK 21 nhưng `javaToolchains` cho biết compiler JDK 17. Class target có thể là Java 17 không?

**Đáp án:** có, nếu compile task được gắn toolchain 17 và release target 17. Kiểm class major bằng `javap` để xác nhận.

### Bài 10 — Reproducibility

Hai CI jobs dùng cùng Wrapper nhưng artifact checksum khác nhau. Có kết luận Wrapper lỗi?

**Đáp án:** chưa. So sánh JDK patch/vendor, OS/architecture, dependencies, plugins, timestamps, locale, generated files, environment parameters và build tasks. Wrapper chỉ pin Gradle/Maven distribution.

## 17. Checklist trước khi merge CI workflow

- [ ] Gradle/Maven Wrapper scripts và bootstrap files cần thiết đã được commit.
- [ ] Wrapper distribution URL dùng HTTPS và version cố định.
- [ ] Gradle `distributionSha256Sum` hoặc Maven checksum fields được đặt từ nguồn chính thức, nếu wrapper version hỗ trợ.
- [ ] Wrapper JAR/bootstrap code đã được validate/review.
- [ ] CI gọi `./gradlew` hoặc `./mvnw`, không dùng global Gradle/Maven ngoài ý muốn.
- [ ] JDK vendor/major/patch và architecture được định nghĩa rõ; Java toolchain/compiler release khớp contract.
- [ ] Plugin versions, dependency versions/BOM và repository policies được pin.
- [ ] Gradle dependency locks/verification metadata được review hoặc Maven strict checksum/repository policy được áp dụng.
- [ ] Runner OS/container/action versions có chính sách pinning và update.
- [ ] Locale/timezone/encoding/build parameters được chuẩn hóa khi ảnh hưởng output.
- [ ] Cache key bao gồm các inputs quan trọng; build vẫn đúng khi cache rỗng.
- [ ] Không cache secrets, private keys hoặc artifacts từ untrusted PR vào release cache.
- [ ] CI log chỉ in thông tin môi trường cần thiết, không dump secrets.
- [ ] Build chạy clean tests và tạo đúng Spring Boot executable JAR.
- [ ] CI ghi lại toolchain versions, source commit và build invocation để chẩn đoán.
- [ ] Wrapper/JDK/plugin upgrades có PR review, compatibility tests và security update cadence.

**Kết luận:** Wrapper đảm bảo dự án tự chỉ định đúng Gradle/Maven distribution; Java toolchain và compiler release đảm bảo build dùng đúng JDK/bytecode; CI runner/container, plugins, dependencies và environment phải được kiểm soát riêng. Dùng Wrapper trong mọi job, xác minh distribution checksum, pin JDK/build inputs, giữ dependency verification và coi cache là tối ưu hiệu năng. Nhờ vậy một commit có thể được build/test trên CI với những đầu vào minh bạch, có thể audit và tái hiện khi cần.

## 18. Tài liệu chính thức

- Gradle — The Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- Gradle — Gradle Wrapper Validation: https://docs.gradle.org/current/userguide/gradle_wrapper.html#sec:verification
- Gradle — Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle — Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
- Gradle — Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
- Gradle — Build Cache: https://docs.gradle.org/current/userguide/build_cache.html
- Apache Maven — Maven Wrapper: https://maven.apache.org/tools/wrapper/
- Apache Maven Wrapper Plugin: https://maven.apache.org/wrapper/maven-wrapper-plugin/
- Apache Maven — Maven Toolchains: https://maven.apache.org/guides/mini/guide-using-toolchains.html
- Apache Maven — Reproducible Builds: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- GitHub Actions — Secure use reference: https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions
- GitHub Actions — Dependency caching: https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows

Các option Wrapper và action syntax có thể thay đổi theo version. Khi nâng Gradle/Maven Wrapper, plugin hoặc CI action, đọc tài liệu đúng version đang pin, kiểm checksum chính thức và chạy clean build trên runner mục tiêu trước khi phát hành.
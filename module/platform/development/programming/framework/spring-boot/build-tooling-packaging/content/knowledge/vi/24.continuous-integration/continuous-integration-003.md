# Cấu hình cache dependency theo công cụ, hệ điều hành và tệp cấu hình

## 1. Mục tiêu trong quy trình Tự động hóa CI

Trong CI, mỗi lần build Spring Boot có thể cần tải hàng trăm artifact: Spring Framework, Jackson, logging libraries, Maven/Gradle plugins, annotation processors và dependency bắc cầu. Nếu runner luôn bắt đầu với thư mục cache rỗng, thời gian chờ repository/network có thể chiếm phần đáng kể của pipeline.

**Dependency cache** lưu artifact và metadata mà build tool đã tải để những lần build sau dùng lại. Một cấu hình tốt phải trả lời bốn câu hỏi:

1. Cache loại dữ liệu nào: Maven local repository, Gradle dependency cache, wrapper distribution, Docker BuildKit package cache hay task-output build cache?
2. Cache nằm ở đâu trên Linux, macOS, Windows, container và CI runner?
3. Khi nào được dùng lại: cache key có phản ánh build tool, OS/architecture, JDK, wrapper/tool version, repository identity và các tệp quyết định dependency graph không?
4. Ai được phép đọc/ghi cache, đặc biệt khi pipeline có pull request từ branch hoặc fork không tin cậy?

Bài này hướng dẫn cấu hình Maven, Gradle, GitHub Actions, GitLab CI và Docker BuildKit. Mục tiêu là **tăng tốc nhưng vẫn giữ tính đúng đắn và khả năng truy xuất nguồn gốc**. Cache là tối ưu hiệu năng; build phải vẫn đúng khi cache trống, hết hạn hoặc bị xóa.

### Kết quả học tập

Sau bài này, bạn có thể:

- Phân biệt dependency cache, wrapper cache, task-output build cache, Docker layer cache, BuildKit cache mount và build artifacts.
- Xác định cache paths của Maven/Gradle trên Windows, Linux và macOS.
- Chọn đúng tệp cấu hình đưa vào cache key cho project đơn và monorepo.
- Tách cache theo tool, OS, architecture, JDK/tool version và repository configuration khi cần.
- Cấu hình Maven/Gradle local cache và kiểm tra offline build.
- Viết GitHub Actions workflow dùng actions/setup-java hoặc gradle/actions/setup-gradle.
- Viết GitLab CI cache key dựa trên nội dung file dependency.
- Tận dụng BuildKit cache mount và hiểu giới hạn trên ephemeral builders.
- Tránh cache nhầm target/, build/ hoặc credentials.
- Chẩn đoán cache miss, cache stale, dependency download lặp lại và cache poisoning.

## 2. Phân biệt các loại cache

Từ “cache” thường được dùng cho nhiều cơ chế khác nhau. Không nên gom chúng vào một thư mục hoặc một key duy nhất.

| Loại | Nội dung | Ví dụ | Mục tiêu |
| --- | --- | --- | --- |
| **Dependency cache** | JAR, POM, module metadata đã resolve/tải | Maven .m2/repository; Gradle caches/modules-2 | Tránh tải dependency lại |
| **Wrapper/tool cache** | Bản phân phối Maven/Gradle do wrapper tải | .m2/wrapper/dists; .gradle/wrapper/dists | Tránh tải build tool distribution lại |
| **Build cache** | Output của task có thể tái sử dụng khi input giống nhau | Gradle local/remote build cache | Tránh thực hiện lại compile/test/task |
| **Docker layer cache** | Kết quả Dockerfile instructions | BuildKit cache records | Tránh chạy lại instruction không đổi |
| **BuildKit cache mount** | Package-manager/compiler data trong lúc RUN | RUN --mount=type=cache | Giữ repository giữa các build trên cùng builder |
| **CNB cache** | Buildpack-contributed layers và lifecycle cache | Buildpacks build/launch cache volumes | Tái sử dụng layer trong quy trình Buildpacks |
| **Artifact** | Output cần chuyển giao hoặc phát hành | JAR, test report, SBOM, image | Chuyển kết quả build sang job/stage/deployment |

**Cache khác artifact.** Cache có thể bị xóa, hết hạn hoặc không được restore mà pipeline vẫn phải chạy đúng. Artifact là kết quả được tạo ra để job khác sử dụng/phát hành; ví dụ JAR ở job build cần được chuyển bằng artifact mechanism, không dựa vào việc JAR tình cờ còn trong cache.

- Maven .m2/repository là dependency/plugin cache; target/classes và target/*.jar là build output.
- Gradle ~/.gradle/caches/modules-2 là dependency cache; Gradle build cache lưu task outputs.
- Docker layer cache giữ kết quả instruction; BuildKit cache mount giữ repository package manager bên trong RUN.
- CNB build cache không đồng nghĩa Maven local repository trên host.

## 3. Thiết kế cache key

Cache key quyết định khi nào build được phép khôi phục dữ liệu đã lưu. Một cấu trúc dễ hiểu cho dự án Java:

~~~text
<tool>-<os>-<arch>-<jdk>-<tool-version>-<repo-profile>-<dependency-config-hash>
~~~

Ví dụ:

~~~text
maven-linux-amd64-jdk17-wrapper-internal-mirror-a84f...
gradle-windows-amd64-jdk17-wrapper-locks-b31c...
maven-macos-arm64-jdk21-central-7f2a...
~~~

| Yếu tố | Vì sao ảnh hưởng? | Cách đưa vào key |
| --- | --- | --- |
| Build tool | Maven và Gradle có cache format khác nhau | Prefix maven hoặc gradle |
| OS | Native dependencies, permissions và path khác nhau | linux, windows, macos |
| Architecture | Native classifier có thể khác amd64/arm64 | x64, arm64 |
| JDK major/vendor | Profile, toolchain hoặc native dependency có thể phụ thuộc JDK | jdk17-temurin, jdk21 |
| Wrapper/tool version | Gradle cache format và plugin behavior phụ thuộc phiên bản | Hash wrapper properties hoặc prefix version |
| Dependency config | Version/catalog/lockfile thay đổi dependency graph | Hash tệp cấu hình |
| Repository identity | Metadata và nguồn package có thể khác giữa repositories | Prefix hoặc config đã loại secrets |
| Trust boundary | Cache từ job không tin cậy không nên dùng cho release | Namespace protected/untrusted riêng |

**Không dùng commit SHA của toàn bộ source làm key chính.** Mỗi commit Java code sẽ tạo cache mới dù POM/lockfiles không đổi. Cũng không hash toàn bộ repository nếu mục tiêu là tái sử dụng dependency cache qua thay đổi source.

### 3.1. Tệp cấu hình cần hash

**Maven:**

- Tất cả pom.xml trong reactor: root, module và parent POM nằm trong repository.
- .mvn/wrapper/maven-wrapper.properties.
- .mvn/extensions.xml nếu dùng build extensions.
- .mvn/maven.config nếu có active profiles, properties hoặc options ảnh hưởng dependency resolution.
- File BOM/version catalog do dự án quản lý nếu nằm ngoài POM.
- Repository/mirror identity và profile ảnh hưởng nguồn resolve.

**Gradle:**

- settings.gradle hoặc settings.gradle.kts.
- build.gradle/build.gradle.kts ở root và subprojects.
- gradle.properties.
- gradle/wrapper/gradle-wrapper.properties.
- gradle/libs.versions.toml và các version catalogs khác.
- gradle.lockfile hoặc gradle/dependency-locks/*.lockfile.
- gradle/verification-metadata.xml.
- buildSrc/, build-logic/ và included builds.
- Repository/plugin management trong settings.gradle(.kts).

**Monorepo:** hash mọi POM/build files/lockfiles của module có thể được build trong job. Nếu chỉ hash root POM mà bỏ module POM hoặc version catalog, cache có thể được restore dù dependency graph đã đổi.

### 3.2. Tệp không nên cache

- ~/.m2/settings.xml nếu chứa username/password, server tokens hoặc private credentials.
- ~/.gradle/gradle.properties nếu chứa credentials.
- .env, private keys, registry tokens và secret files.
- Toàn bộ source code chỉ để làm dependency cache key.
- target/ hoặc build/ nếu mục tiêu chỉ là cache dependency.

Không đưa secrets vào cache archive hoặc key. Nếu repository mirror thay đổi, dùng repository ID hoặc file config đã loại secrets để phân biệt cache.

## 4. Cache paths theo tool và hệ điều hành

### 4.1. Maven

Maven local repository mặc định nằm trong .m2/repository dưới user home. Nó chứa dependencies, plugin artifacts, POM metadata và thông tin repository.

| Hệ điều hành | Maven local repository |
| --- | --- |
| Linux | $HOME/.m2/repository |
| macOS | $HOME/.m2/repository |
| Windows PowerShell | $env:USERPROFILE\.m2\repository |
| Windows CMD | %USERPROFILE%\.m2\repository |

Maven Wrapper distribution cache thường ở .m2/wrapper/dists, tách khỏi local repository.

Kiểm tra effective settings:

~~~bash
mvn help:effective-settings
~~~

Tìm phần localRepository. Nếu không cấu hình, Maven dùng vị trí mặc định theo user home.

### 4.2. Gradle

Gradle User Home mặc định là ~/.gradle trên Linux/macOS và %USERPROFILE%\.gradle trên Windows. Có thể đổi bằng GRADLE_USER_HOME.

| Nội dung | Linux/macOS | Windows |
| --- | --- | --- |
| Dependency artifacts/metadata | $GRADLE_USER_HOME/caches/modules-2 | %USERPROFILE%\.gradle\caches\modules-2 |
| Gradle wrapper distributions | ~/.gradle/wrapper/dists | %USERPROFILE%\.gradle\wrapper\dists |
| Version-specific caches | ~/.gradle/caches/<version>/ | %USERPROFILE%\.gradle\caches\<version>\ |
| Project-local state | <project>/.gradle/ | <project>\.gradle\ |

Với cấu hình mặc định, $GRADLE_USER_HOME là $HOME/.gradle; do đó dependency cache thực tế nằm ở **$GRADLE_USER_HOME/caches/modules-2**. Gradle quản lý artifacts và metadata trong các thư mục này; thông thường không cần tự chọn từng file.

Đặt Gradle User Home riêng trong CI:

~~~bash
export GRADLE_USER_HOME="$PWD/.gradle-user-home"
./gradlew --no-daemon build
~~~

Windows PowerShell:

~~~powershell
$env:GRADLE_USER_HOME = Join-Path $PWD ".gradle-user-home"
.\gradlew.bat --no-daemon build
~~~

Nếu đặt Gradle User Home trong workspace, CI phải cache đúng .gradle-user-home/caches và .gradle-user-home/wrapper. Không để Gradle ghi vào ~/.gradle trong khi CI chỉ lưu thư mục khác.

### 4.3. Vì sao phải tách cache theo OS/architecture?

Các JAR Java thuần thường portable, nhưng dependency graph có thể khác do Maven profiles kích hoạt theo OS/JDK, Gradle variant attributes, native classifiers, JNI libraries, permissions, path, plugin logic hoặc toolchains. Vì vậy cache linux/amd64 không nên mặc định dùng cho windows/amd64 hay linux/arm64.

## 5. Cấu hình cache cho Maven

### 5.1. Dùng local repository mặc định

~~~bash
mvn -B -ntp verify
~~~

Maven tìm dependencies trong ~/.m2/repository trước khi tải từ remote repositories. Nếu cần chỉ định đường dẫn riêng:

~~~bash
mvn -Dmaven.repo.local="$HOME/.m2/repository" -B -ntp verify
~~~

Windows PowerShell:

~~~powershell
mvn "-Dmaven.repo.local=$env:USERPROFILE\.m2\repository" -B -ntp verify
~~~

### 5.2. Đổi local repository qua settings.xml

File user settings thường nằm ở ~/.m2/settings.xml; Windows ở %USERPROFILE%\.m2\settings.xml.

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <localRepository>/opt/build-cache/maven-repository</localRepository>
</settings>
~~~

/opt/build-cache/... là ví dụ Linux; trên Windows/macOS cần đường dẫn hợp lệ. settings.xml cũng có thể chứa mirror, proxy, profiles và credentials; **không cache toàn bộ user settings**.

Trong CI, dùng -Dmaven.repo.local thường dễ kiểm soát hơn vì có thể đặt repository vào thư mục workspace mà CI cho phép cache.

### 5.3. Maven key theo POM và wrapper

~~~text
maven-linux-amd64-jdk17-<hash-of-pom-and-maven-config>
~~~

Các tệp quan trọng:

~~~text
pom.xml
**/pom.xml
.mvn/wrapper/maven-wrapper.properties
.mvn/extensions.xml
.mvn/maven.config
~~~

Với multi-module, bao gồm root POM và mọi module POM. Nếu CI profile thay đổi dependencies, đưa profile name vào prefix hoặc hash file config an toàn thể hiện profile đó.

### 5.4. SNAPSHOT và dynamic versions

Cache không làm dependency biến động trở nên bất biến:

- Release dependency có version cố định thường tái sử dụng ổn định.
- SNAPSHOT và repository metadata có thể thay đổi theo thời gian.
- Version ranges hoặc dependency version không pin có thể resolve thành version khác.
- Maven -U yêu cầu kiểm tra cập nhật snapshot và các release thiếu/đã cập nhật theo chính sách resolver.

Refresh có chủ đích:

~~~bash
mvn -U -B -ntp verify
~~~

Không dùng -U trong mọi build chỉ vì muốn “làm mới cache”; nó có thể tăng truy vấn repository. Với release, ưu tiên version được pin và dependency management rõ ràng.

### 5.5. Kiểm tra cache Maven có đủ

Sau khi warm cache:

~~~bash
mvn -o -B -ntp verify
~~~

-o là offline mode. Nếu build báo thiếu artifact/plugin, cache chưa chứa toàn bộ inputs mà lệnh build cần. Đây là phép kiểm tra độ đầy đủ, không phải cấu hình mặc định của pipeline.

dependency:go-offline hữu ích để warm một phần dependencies/plugins, nhưng không bảo đảm mọi plugin/profile động đã tải đủ. Hãy xác nhận bằng đúng lệnh CI, chẳng hạn mvn verify với các profiles cần thiết.

## 6. Cấu hình cache cho Gradle

### 6.1. Dependency cache và wrapper cache

Gradle quản lý dependency cache dưới Gradle User Home, chủ yếu trong caches/modules-2. Wrapper distributions được lưu riêng trong wrapper/dists.

~~~bash
./gradlew --no-daemon build
~~~

Windows:

~~~powershell
.\gradlew.bat --no-daemon build
~~~

Không chỉ cache thư mục project .gradle/ rồi kỳ vọng đã cache toàn bộ dependencies. Đó là project-local state; dependency cache chính nằm trong Gradle User Home.

### 6.2. Tệp cần hash

~~~text
settings.gradle(.kts)
build.gradle(.kts)
gradle.properties
gradle/wrapper/gradle-wrapper.properties
gradle/libs.versions.toml
gradle.lockfile
gradle/verification-metadata.xml
buildSrc/**
build-logic/**
~~~

Trong monorepo, thêm build files và lockfiles của subprojects/included builds. Nếu dùng nhiều version catalogs, thêm tất cả file catalog.

### 6.3. Dependency cache khác Gradle build cache

Gradle có build cache riêng, bật bằng:

~~~bash
./gradlew --build-cache build
~~~

Hoặc trong gradle.properties:

~~~properties
org.gradle.caching=true
~~~

Dependency cache giữ module metadata/artifacts đã resolve. Build cache giữ **task outputs** có thể tái sử dụng khi task inputs tương ứng giống nhau. Có thể dùng cả hai nhưng chúng có mục đích và invalidation khác nhau.

### 6.4. Offline và refresh

Kiểm tra dependency cache:

~~~bash
./gradlew --offline build
~~~

Khi cần kiểm tra lại dependency metadata hoặc changing/dynamic dependencies:

~~~bash
./gradlew --refresh-dependencies build
~~~

Gradle kiểm tra metadata/checksums và chỉ tải lại những gì thực sự cần thiết; --refresh-dependencies không có nghĩa luôn tải lại tất cả JAR.

Gradle cache metadata có tính repository-specific và cache format liên quan phiên bản Gradle. Nên dùng cùng wrapper version khi tạo và tiêu thụ cache. Không copy tùy tiện cache đã ghi bởi phiên bản khác.

### 6.5. Dependency locking và verification

Để cache không che khuất rủi ro supply chain:

- Bật dependency locking cho configurations phù hợp và version-control lockfiles.
- Dùng gradle/verification-metadata.xml để xác minh checksums/signatures khi policy yêu cầu.
- Khi thêm dependency, review thay đổi lockfile và verification metadata.
- Không xem cache hit là bằng chứng artifact đã được xác minh.

Tạo checksum metadata ban đầu:

~~~bash
./gradlew --write-verification-metadata sha256
~~~

Lệnh này bootstrap checksum từ artifacts đang được resolve; **phải review kết quả và xác minh nguồn đáng tin** trước khi commit.

## 7. GitHub Actions: cache Maven theo OS và POM

GitHub-hosted runners thường bắt đầu bằng môi trường sạch. Dùng actions/setup-java để cấu hình Java và dependency cache.

### 7.1. Maven project đơn

File .github/workflows/maven.yml:

~~~yaml
name: Maven build

on:
  push:
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Build and test
        run: ./mvnw -B -ntp verify
~~~

cache: maven bật cache local Maven repository. Action tạo key theo runner OS, architecture, package manager và hash các tệp dependency. Wrapper distribution và JDK có thể được cache riêng.

### 7.2. Maven monorepo hoặc cấu hình tùy chỉnh

~~~yaml
      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
          cache-dependency-path: |
            **/pom.xml
            .mvn/wrapper/maven-wrapper.properties
            .mvn/extensions.xml
            .mvn/maven.config
~~~

Các glob làm key đổi khi POM, Maven wrapper, extensions hoặc Maven CLI config đổi. Nếu project dùng file version catalog/BOM riêng, thêm chúng vào danh sách.

**Lưu ý về Java matrix:** dependency cache key của setup-java gồm OS/architecture/package manager/file hash; JDK installation cache là một cache riêng. Nếu matrix dùng nhiều JDK nhưng cùng dependency graph, có thể tái sử dụng dependency cache. Nếu OS/JDK profile hoặc native dependencies làm nội dung resolve khác nhau, dùng namespace tách biệt theo policy.

### 7.3. Restore prefix khi tự quản lý cache

Nếu dùng actions/cache trực tiếp, có thể thiết kế:

~~~yaml
key: maven-OS-ARCH-jdk17-DEPENDENCY_CONFIG_HASH
restore-keys: |
  maven-OS-ARCH-jdk17-
~~~

Key đầy đủ được ưu tiên; restore-keys là fallback để khôi phục cache gần nhất cùng platform/toolchain. Không dùng fallback quá rộng kiểu chỉ maven-, vì có thể khôi phục cache từ OS/architecture/JDK không tương thích.

## 8. GitHub Actions: cache Gradle

### 8.1. Dùng Gradle setup action

~~~yaml
name: Gradle build

on:
  push:
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'

      - uses: gradle/actions/setup-gradle@v6

      - name: Build and test
        run: ./gradlew --no-daemon build
~~~

gradle/actions/setup-gradle quản lý cache của Gradle User Home và hỗ trợ các tính năng cache nâng cao. Nếu dùng action này, không thêm action khác cache trùng ~/.gradle/caches trừ khi có lý do rõ ràng.

### 8.2. Hash các tệp Gradle trong monorepo

Khi dùng actions/setup-java với cache: gradle:

~~~yaml
      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: gradle
          cache-dependency-path: |
            **/*.gradle*
            **/gradle.properties
            **/gradle-wrapper.properties
            **/gradle.lockfile
            gradle/libs.versions.toml
            gradle/verification-metadata.xml
            buildSrc/**
            build-logic/**
~~~

Danh sách phải khớp cấu trúc repository. Nếu version catalog nằm ở đường dẫn khác hoặc có nhiều included builds, bổ sung các file liên quan. **Chọn một cơ chế quản lý chính**, tránh hai action cùng restore/save một thư mục Gradle.

## 9. GitLab CI: key theo nội dung file và cache path

GitLab CI cho phép cache:key:files tạo key dựa trên nội dung tệp. cache:paths chỉ định thư mục tương đối với project directory.

### 9.1. Maven trên Linux runner

File .gitlab-ci.yml:

~~~yaml
maven-build:
  image: maven:3.9-eclipse-temurin-17
  cache:
    key:
      prefix: "maven-linux-amd64-jdk17"
      files:
        - pom.xml
        - .mvn/wrapper/maven-wrapper.properties
        - .mvn/extensions.xml
        - .mvn/maven.config
    paths:
      - .m2/repository/
    policy: pull-push
  script:
    - mvn -Dmaven.repo.local="$CI_PROJECT_DIR/.m2/repository" -B -ntp verify
~~~

Maven local repository được chuyển vào $CI_PROJECT_DIR/.m2/repository, nằm trong workspace để GitLab Runner có thể cache. Key được tách theo platform/toolchain prefix và hash tệp cấu hình.

Với Windows runner, dùng prefix khác, ví dụ maven-windows-amd64-jdk17, và điều chỉnh command/path cho PowerShell/CMD. Không dùng chung cache Linux và Windows chỉ vì cùng Maven version.

### 9.2. Gradle trên Linux runner

~~~yaml
gradle-build:
  image: eclipse-temurin:17-jdk
  cache:
    key:
      prefix: "gradle-linux-amd64-jdk17"
      files:
        - settings.gradle
        - build.gradle
        - gradle/wrapper/gradle-wrapper.properties
        - gradle/libs.versions.toml
        - gradle.lockfile
        - gradle/verification-metadata.xml
    paths:
      - .gradle-user-home/caches/
      - .gradle-user-home/wrapper/
    policy: pull-push
  script:
    - GRADLE_USER_HOME="$CI_PROJECT_DIR/.gradle-user-home" ./gradlew --no-daemon build
~~~

Nếu project dùng Kotlin DSL, thay bằng settings.gradle.kts và build.gradle.kts. Thêm subproject build files, lockfiles và build logic theo cấu trúc thực tế. GitLab cache:key:files hỗ trợ tối đa 10 tệp; chọn các file gốc quyết định version catalog/lockfiles hoặc thiết kế một checksum manifest được quản lý có kiểm soát.

### 9.3. pull, push và pull-push

- pull-push: job khôi phục cache và upload cache mới sau khi chạy.
- pull: chỉ tiêu thụ cache, không upload lại; phù hợp job fan-out/matrix.
- push: chỉ upload cache, không khôi phục trước; phù hợp cache-warming job trong một số pipeline.

Nhiều writer dùng cùng key có thể tạo race hoặc cache bị ghi đè. Nên có một job warm/cache writer chính và các job còn lại chỉ pull nếu cần. Cache availability phụ thuộc runner executor và distributed cache configuration; **không bảo đảm** mọi job luôn thấy cùng cache.

### 9.4. Cache khác artifacts trong GitLab

- **Cache:** dependency downloads để tái sử dụng giữa pipeline/job; có thể hết hạn hoặc bị clear.
- **Artifacts:** output do job tạo ra để job ở stage sau dùng, ví dụ JAR, test reports, SBOM hoặc scan report.

Không đặt cùng đường dẫn vào cả cache và artifacts nếu không có chủ đích. Cache được restore trước artifacts; artifact có thể ghi đè file trong workspace. Với JAR cần deploy, truyền bằng artifacts hoặc registry, không dựa vào dependency cache.

## 10. Docker BuildKit: cache Maven repository trong build stage

Khi Dockerfile chạy Maven trong build stage, mỗi lần build container filesystem mới có thể tải lại dependencies. BuildKit hỗ trợ cache mount để giữ repository data giữa các lần RUN trên cùng builder.

~~~dockerfile
# syntax=docker/dockerfile:1
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace

COPY pom.xml ./
COPY .mvn/ .mvn/

RUN --mount=type=cache,id=catalog-maven-linux-amd64-jdk17,target=/root/.m2/repository,sharing=locked \
    mvn -B -ntp dependency:go-offline

COPY src ./src

RUN --mount=type=cache,id=catalog-maven-linux-amd64-jdk17,target=/root/.m2/repository,sharing=locked \
    mvn -B -ntp verify
~~~

- target=/root/.m2/repository phải khớp Maven local repository của user trong build container.
- id= tạo namespace riêng để tránh chia sẻ cache giữa tool/project/platform không tương thích.
- sharing=locked yêu cầu writer thứ hai chờ khi cache đang được dùng.
- Cả hai RUN phải mount cùng cache ID/path để dùng chung Maven repository.
- dependency:go-offline giúp warm cache, nhưng không bảo đảm mọi plugin/profile động đã có; verify vẫn phải resolve đầy đủ.
- Nếu build cần .mvn/extensions.xml, maven.config, wrapper hoặc parent POM, phải copy chúng trước lệnh Maven tương ứng.

### 10.1. Cache mount không phải Docker layer cache

Docker BuildKit cache mount lưu dữ liệu package manager tại builder-local storage. Nó có thể còn qua nhiều build trên cùng builder, nhưng:

- Không được đưa vào final image như file system layer thông thường.
- Không tự động được export trong --cache-to hoặc restore bằng --cache-from.
- Nếu CI tạo builder/máy mới cho mỗi job, cache mount bắt đầu rỗng.
- Build phải chạy đúng ngay cả khi cache mount trống hoặc bị garbage collection.

Nếu runner ephemeral, cân nhắc persistent BuildKit builder, external dependency cache riêng, Maven repository proxy hoặc cơ chế cache do CI provider quản lý. Docker layer cache export/import và BuildKit cache mount là hai cơ chế khác nhau.

Với Gradle trong Docker, mount Gradle User Home phù hợp với user chạy build, ví dụ caches và wrapper. Không hardcode /root/.gradle nếu image chạy bằng user gradle hoặc UID khác. Kiểm tra GRADLE_USER_HOME thực tế và tách cache ID theo Gradle wrapper version/OS/architecture.

## 11. Cache trong Cloud Native Buildpacks

Nếu Spring Boot dùng spring-boot:build-image hoặc Gradle bootBuildImage, CNB có build cache và launch cache riêng do lifecycle quản lý.

Đây **không phải cùng cache** với Maven .m2/repository hoặc Gradle caches/modules-2 trên host. CNB cache thường được giữ trong Docker volumes/Buildpacks builder infrastructure, phụ thuộc image name, builder, lifecycle và cấu hình plugin.

Khi CI dùng Buildpacks:

- Giữ builder/run image và cache naming ổn định theo release policy.
- Kiểm tra Docker volumes/cache có tồn tại qua các pipeline hay không.
- Tránh tạo image name ngẫu nhiên mỗi job nếu mục tiêu là reuse cache.
- Dọn cache theo retention/size policy, không xóa mọi volume sau mỗi build.
- Không coi CNB cache hit là bằng chứng dependency được pin hoặc verified.
- Nếu Maven/Gradle build trước khi gọi build-image, vẫn cần cache dependency của build tool riêng.

## 12. Chiến lược key thực tế

**Maven project đơn:**

~~~text
maven-<os>-<arch>-jdk17-<maven-wrapper-hash>-<pom-hash>
~~~

Hash root pom.xml, wrapper properties và .mvn/extensions.xml. Nếu mirror/profile thay đổi, bổ sung repository identity hoặc file cấu hình an toàn.

**Maven monorepo:**

~~~text
maven-<os>-<arch>-jdk17-<reactor-config-hash>
~~~

Hash tất cả module POMs và Maven config liên quan. Tránh hash toàn bộ source tree.

**Gradle với version catalog và locking:**

~~~text
gradle-<os>-<arch>-jdk17-<wrapper-version>-<catalog-lock-verification-hash>
~~~

Bao gồm wrapper properties, settings/build scripts, version catalog, dependency lockfiles và verification metadata. Khi thay version trong catalog hoặc lockfile, cache key đổi.

**Multi-JDK/OS matrix:**

~~~text
maven-linux-amd64-jdk17-...
maven-linux-arm64-jdk17-...
maven-windows-amd64-jdk17-...
maven-macos-arm64-jdk21-...
~~~

Nếu artifact hoàn toàn portable, một số cache có thể dùng chung về mặt kỹ thuật, nhưng tách key an toàn hơn khi profile/native classifiers hoặc toolchain thay đổi. Tối ưu sau khi đo.

**Restore prefix:** khi key hash thay đổi, một restore prefix có thể lấy cache cũ cùng tool/platform. Không fallback qua tool khác hoặc OS khác. Sau khi restore fallback, Maven/Gradle vẫn phải kiểm tra dependency resolution theo cấu hình hiện tại.

## 13. Bảo mật và tính đúng đắn

### 13.1. Cache là dữ liệu đầu vào, không phải nguồn chân lý

Một job có quyền ghi cache có thể lưu nội dung sai hoặc bị sửa. Vì vậy:

- Không dùng cache làm bằng chứng dependency đến từ repository đáng tin.
- Dùng dependency verification/checksums/signatures khi policy yêu cầu.
- Giữ lockfiles và dependency versions trong version control.
- Scan và validate artifact sau khi build.
- Có thể xóa cache và build lại mà không làm thay đổi source of truth.

### 13.2. Không cache credentials

Chỉ cache những thư mục chứa dependency/tool distributions cần thiết:

- Maven: .m2/repository và wrapper distributions nếu cần.
- Gradle: caches và wrapper phù hợp.
- Không cache toàn bộ user home nếu trong đó có settings, credentials, init scripts riêng hoặc secret files.
- Không đặt registry tokens, Maven server passwords, signing keys hoặc private keys vào cache paths.

### 13.3. Tách cache giữa trusted và untrusted jobs

Pull request từ fork/branch không tin cậy có thể chạy script build và ghi dữ liệu vào cache mà nó được cấp quyền sử dụng. Với release pipeline:

- Dùng cache namespace/permissions tách biệt cho protected branches.
- Không để release job tin tưởng cache có thể bị ghi bởi untrusted workflow.
- Có thể cho PR job read-only cache nếu CI provider hỗ trợ.
- Chỉ một job trusted làm cache writer cho cache dùng trong release.
- Không chia sẻ cache private dependency giữa projects/tenants nếu policy không cho phép.

GitLab có phân tách cache protected và non-protected branches trong cấu hình phổ biến; GitHub Actions có cache scope/access rules riêng. Hãy kiểm tra provider và repository policy của tổ chức.

### 13.4. Cache và checksum

Gradle dependency verification có thể dùng gradle/verification-metadata.xml để kiểm tra artifact checksums/signatures. File này nên được review và version-control. Cache hit không được bỏ qua verification.

Với Maven, dùng repositories đáng tin, release versions được pin, checksum policy và repository manager nội bộ nếu tổ chức cần kiểm soát artifact nguồn. Không tắt checksum verification chỉ để cache/build “xanh”.

## 14. Chẩn đoán cache hit, miss và cache stale

Kiểm tra đường dẫn:

~~~bash
mvn help:effective-settings
mvn -version
./gradlew --version
./gradlew --status
~~~

Xác nhận CI đang dùng đúng user home, cache path và wrapper. Cache được lưu ở ~/.m2/repository sẽ không giúp build nếu command đặt -Dmaven.repo.local sang đường dẫn khác.

**Kiểm tra offline:**

~~~bash
mvn -o -B -ntp verify
./gradlew --offline --no-daemon build
~~~

Nếu offline build fail, đọc artifact/plugin/configuration bị thiếu. Không xóa toàn bộ cache ngay lập tức; có thể chỉ thiếu plugin profile hoặc module chưa được warm.

**Buộc refresh khi cần:**

~~~bash
mvn -U -B -ntp verify
./gradlew --refresh-dependencies build
~~~

Dùng khi có thay đổi snapshot/dynamic dependency hoặc nghi metadata cache stale. Không biến refresh thành bước mặc định cho mọi pipeline.

Theo dõi cache exact hit, fallback hit, miss, thời gian restore/download, dependency resolution, kích thước archive, thời gian build khi cache trống/hit và tần suất invalidation. Nếu cache 2 GB mất nhiều thời gian tải hơn việc tải dependency nhỏ, giảm phạm vi cache hoặc dùng runner có persistent storage.

## 15. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Maven tải dependency lại mỗi job | Cache path không trùng maven.repo.local hoặc runner mới không restore cache | In effective settings, kiểm tra cache path và key |
| Maven cache key không đổi khi module POM đổi | Chỉ hash root POM | Thêm **/pom.xml hoặc toàn reactor POMs |
| Maven cache chứa settings/credentials | Cache toàn bộ .m2 | Chỉ cache .m2/repository và wrapper distributions |
| Maven offline fail ở plugin | Warm dependency goal chưa tải plugin/profile cần thiết | Chạy đúng Maven goals/profiles CI cần |
| SNAPSHOT cũ vẫn được dùng | Snapshot metadata còn trong cache | Dùng -U có chủ đích hoặc tránh SNAPSHOT ở release |
| Gradle tải lại module metadata | Cache path khác GRADLE_USER_HOME hoặc repo identity đổi | Kiểm tra Gradle User Home/repositories |
| Gradle cache không tương thích | Dùng cache format/Gradle version khác | Key theo wrapper version |
| Gradle build outputs không được tái sử dụng | Chỉ bật dependency cache | Bật Gradle build cache riêng khi task hỗ trợ |
| Windows và Linux dùng chung cache | Key thiếu OS/architecture | Tách cache namespace theo runner platform |
| Cache không đổi khi version catalog đổi | Key thiếu libs.versions.toml | Thêm version catalog vào hash |
| Cache không đổi khi lockfile đổi | Lockfile chưa nằm trong key | Thêm lockfiles/verification metadata |
| Cache miss mọi commit | Key chứa commit SHA hoặc toàn source | Hash chỉ dependency/build configuration files |
| GitHub Actions restore cache cũ nhưng build vẫn tải thêm | Fallback key hit hoặc cache chưa chứa artifacts mới | Tạo key mới khi config đổi, seed cache đầy đủ |
| GitLab jobs ghi đè cache của nhau | Cùng key nhưng khác paths/writers | Tách key hoặc dùng pull-only consumer |
| GitLab job không tìm thấy cache | Runner khác máy và không có distributed cache | Dùng distributed cache hoặc persistent runner |
| BuildKit cache mount trống trên CI | Builder mới, cache mount là builder-local | Dùng persistent builder hoặc external dependency cache |
| Docker layer cache hit nhưng Maven vẫn tải lại | Layer cache và cache mount khác cơ chế | Mount đúng .m2/repository trong mọi RUN cần thiết |
| Cache bị phình lớn | Cache quá nhiều version/module/metadata cũ | Giới hạn retention, dọn cache có kiểm soát |
| Cache restore chậm hơn download | Archive quá lớn hoặc network cache yếu | Cache đúng thư mục cần, đo restore cost |
| Build dùng artifact sai từ cache | Cache bị dùng như artifact handoff | Dùng CI artifacts cho JAR/test reports/SBOM |
| Private dependency lộ cho project khác | Cache scope quá rộng | Tách theo project/tenant/permission và repository identity |
| Checksum mismatch sau cache restore | Artifact cache hỏng, repository republish hoặc tampering | Dừng release, xác minh checksum và source |

## 16. Quy trình cấu hình cache theo thứ tự

1. **Xác định build tool và wrapper version.** Ghi nhận Maven/Gradle version, JDK major/vendor và platform.
2. **Xác định cache path thực tế.** Dùng Maven effective settings hoặc GRADLE_USER_HOME; không đoán theo user home của developer.
3. **Phân loại dữ liệu.** Tách dependency artifacts, wrapper distributions, task outputs, Docker cache và release artifacts.
4. **Liệt kê config files.** POMs, wrapper properties, settings/build scripts, version catalogs, lockfiles, profiles và repository identity.
5. **Tạo cache key.** Có tool + OS + architecture + JDK/tool version + config hash; không dùng commit SHA làm key chính.
6. **Thiết lập trust boundary.** Không cache credentials, tách protected/untrusted jobs, giới hạn writer.
7. **Cấu hình provider.** GitHub Actions, GitLab CI, persistent runner hoặc BuildKit cache mounts theo môi trường.
8. **Warm cache bằng lệnh build thật.** Chạy verify/build với đúng profiles và modules; không chỉ chạy lệnh resolve tối giản.
9. **Thử offline và đo.** Kiểm tra cache đủ dùng, đo restore time và download time.
10. **Thiết lập invalidation/refresh.** Khi dependency config đổi thì key đổi; khi cache stale thì refresh theo chính sách.
11. **Lưu artifact riêng.** JAR, reports, SBOM và image digest được truyền bằng artifact/registry, không dựa vào dependency cache.
12. **Theo dõi định kỳ.** Cache size, hit rate, age, security và chi phí vận hành.

## 17. Bài tập tự kiểm tra

**1. Vì sao không nên dùng commit SHA làm cache key chính cho Maven dependencies?**

Đáp án: Mọi commit tạo key mới kể cả khi POM không đổi, khiến dependency cache miss liên tục. Nên hash dependency configuration files.

**2. Maven local repository mặc định ở đâu trên Windows?**

Đáp án: %USERPROFILE%\.m2\repository, trừ khi đổi qua settings.xml hoặc -Dmaven.repo.local.

**3. Gradle dependency cache và Gradle build cache khác nhau thế nào?**

Đáp án: Dependency cache lưu module metadata/artifacts đã resolve; build cache lưu task outputs có thể tái sử dụng theo task inputs.

**4. Vì sao cache key cần OS và architecture?**

Đáp án: OS profiles, native classifiers, JNI libraries, permissions và toolchains có thể khác nhau giữa Linux/Windows/macOS hoặc amd64/arm64.

**5. Một Maven monorepo cần hash những gì?**

Đáp án: Root và module POMs, Maven wrapper properties, extensions, Maven config và các file khác ảnh hưởng profile/repository/dependency resolution.

**6. Một Gradle project dùng version catalog cần đưa file nào vào key?**

Đáp án: gradle/libs.versions.toml cùng build/settings scripts, wrapper properties, lockfiles, gradle.properties và verification metadata khi có.

**7. mvn -o verify dùng để làm gì?**

Đáp án: Chạy Maven offline để kiểm tra cache hiện tại có đủ dependency/plugin cho lệnh build đó không.

**8. ./gradlew --refresh-dependencies build có tải lại mọi JAR không?**

Đáp án: Không. Gradle refresh metadata và kiểm tra artifacts; chỉ tải lại những gì cần thiết.

**9. GitLab cache có thay thế artifacts không?**

Đáp án: Không. Cache tái sử dụng dependency downloads; artifacts chuyển output do job tạo ra sang stage/job khác hoặc lưu lại.

**10. Vì sao BuildKit cache mount có thể rỗng ở CI job tiếp theo?**

Đáp án: Cache mount lưu trong builder-local storage và không được export/import tự động qua --cache-to/--cache-from. Builder ephemeral bắt đầu với cache mount trống.

**11. Có nên cache ~/.m2 toàn bộ không?**

Đáp án: Không nên mặc định. Cache .m2/repository và wrapper distributions cần thiết; giữ settings/credentials ở vùng riêng được bảo vệ.

**12. Vì sao Gradle cache hit vẫn cần dependency verification?**

Đáp án: Cache có thể bị thay đổi hoặc sai nguồn. Verification checksums/signatures xác nhận artifacts theo metadata đã review.

## 18. Checklist áp dụng cho dự án Java/Spring Boot

- [ ] Build command dùng Maven/Gradle Wrapper và version được pin.
- [ ] JDK major/vendor/architecture được ghi nhận trong pipeline.
- [ ] Cache path đúng với maven.repo.local hoặc GRADLE_USER_HOME thực tế.
- [ ] Maven key gồm root/module POMs và .mvn config liên quan.
- [ ] Gradle key gồm settings/build scripts, wrapper, version catalogs, lockfiles và verification metadata.
- [ ] Cache key tách theo tool, OS, architecture và toolchain khi cần.
- [ ] Repository/mirror identity được tính đến nếu có nhiều nguồn artifacts.
- [ ] Không cache credentials, user settings hoặc private keys.
- [ ] Không dùng cache thay artifacts để chuyển JAR/SBOM/test reports.
- [ ] Không cache toàn bộ target/ hoặc build/ như dependency cache.
- [ ] BuildKit cache mounts được tách ID và biết rõ builder persistence.
- [ ] Cache restore/seed được kiểm thử bằng đúng Maven/Gradle build command.
- [ ] Offline build được dùng như phép thử độ đầy đủ khi phù hợp.
- [ ] Dynamic/SNAPSHOT dependencies có refresh/update policy rõ.
- [ ] Lockfiles/checksums/dependency verification được review.
- [ ] Protected/untrusted jobs có cache access boundary.
- [ ] Cache writer/reader policy tránh concurrent overwrite.
- [ ] Cache retention và kích thước được quản lý.
- [ ] Có số liệu hit rate, restore time và build time trước/sau.
- [ ] Build thành công khi cache bị xóa hoặc không restore.

**Kết luận:** Cấu hình cache dependency tốt bắt đầu từ việc chọn **đúng thư mục của đúng build tool**, sau đó tạo key dựa trên **OS/architecture/toolchain và những tệp thực sự quyết định dependency graph**. Maven cần .m2/repository cùng POM/wrapper config; Gradle cần Gradle User Home caches cùng wrapper, version catalogs và lockfiles. CI provider và BuildKit chỉ là nơi lưu/khôi phục những cache đó. Giữ credentials ngoài cache, tách cache khỏi artifacts và luôn bảo đảm build vẫn đúng khi cache trống.

## 19. Tài liệu tham khảo chính thức

1. [Apache Maven — Settings Reference / Local Repository](https://maven.apache.org/settings.html)
2. [Apache Maven — Configuring Maven and Local Repository](https://maven.apache.org/guides/mini/guide-configuring-maven.html)
3. [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html)
4. [Gradle — Directory Layout and Cache Locations](https://docs.gradle.org/current/userguide/directory_layout.html)
5. [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html)
6. [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
7. [GitHub Actions — Dependency Caching Reference](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
8. [GitHub — actions/setup-java Caching and cache-dependency-path](https://github.com/actions/setup-java)
9. [GitHub — gradle/actions/setup-gradle](https://github.com/gradle/actions/tree/main/setup-gradle)
10. [GitLab CI/CD — Caching](https://docs.gitlab.com/ci/caching/)
11. [GitLab CI/CD — cache:key:files and cache:paths](https://docs.gitlab.com/ci/yaml/#cache)
12. [Docker — Dockerfile RUN --mount=type=cache](https://docs.docker.com/reference/dockerfile/#run---mounttypecache)

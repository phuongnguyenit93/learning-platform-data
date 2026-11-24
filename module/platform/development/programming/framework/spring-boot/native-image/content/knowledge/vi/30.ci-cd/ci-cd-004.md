# Cache Gradle, Maven, metadata và buildpack theo đầu vào thích hợp

## 1. Vì sao cần thiết kế cache theo từng lớp?

Trong module **SPRING_BOOT_NATIVE_IMAGE**, pipeline phải giải quyết nhiều công việc tốn thời gian: tải dependency, chạy Spring AOT, biên dịch Native Image, thu thập reachability metadata và đóng gói OCI image bằng Cloud Native Buildpacks. Cache đúng lớp giúp tránh tải hoặc tính toán lại những đầu vào chưa thay đổi.

Không có một thư mục cache duy nhất bao phủ mọi công việc. Gradle, Maven, Native Image và buildpacks có cơ chế lưu trữ, quy tắc hợp lệ và vòng đời riêng. Nếu gom chúng vào một cache key chung, một thay đổi nhỏ có thể làm mất toàn bộ cache; ngược lại, cache quá rộng có thể trả lại output được tạo từ profile, toolchain hoặc nền tảng khác.

Một pipeline tốt phân biệt:

- **Dependency cache:** artifact, plugin, wrapper và metadata đã tải từ repository.
- **Build output cache:** kết quả task có thể tái sử dụng khi toàn bộ input giống nhau.
- **Configuration cache:** mô hình cấu hình Gradle đã được tính toán.
- **AOT và reachability metadata:** generated output cùng metadata phụ thuộc source, classpath, profile và phiên bản toolchain.
- **Buildpack cache:** các layer được buildpack tạo ra trong quá trình build và launch image.
- **OCI/Docker cache:** image layer và dữ liệu của container engine.

Các lớp có thể bổ trợ nhau nhưng không thay thế nhau. Gradle dependency cache không giữ layer của buildpack; buildpack cache không thay thế Maven local repository; reachability metadata không thể dùng chung giữa hai phiên bản thư viện nếu nội dung metadata khác nhau.

## 2. Bản đồ các cache

| Cache | Nội dung | Công cụ quản lý | Đơn vị invalidation chính |
| --- | --- | --- | --- |
| Gradle User Home | Wrapper, dependency, artifact transforms, local build cache và state của Gradle | Gradle, CI action | Gradle version, OS, build files, dependency graph, job/commit |
| Gradle build cache | Output của các task cacheable | Gradle local/remote build cache | Task implementation, input properties, classpath và output declarations |
| Gradle configuration cache | Kết quả cấu hình build | Gradle | Build logic, settings, environment và configuration inputs |
| Maven local repository | Dependency, plugin, POM và repository metadata đã tải | Maven Resolver | GAV, repository origin, release/snapshot metadata |
| Maven build cache | Output của lifecycle/plugin execution đủ điều kiện | Maven Build Cache Extension | Source files, plugin parameters và build environment đã khai báo |
| Spring AOT output | Generated source, classes, resources và initializer | Spring Boot Maven/Gradle plugin | Classpath, source, AOT profile/arguments và condition inputs |
| Native reachability metadata | Reflection, JNI, resource, serialization và metadata khác | GraalVM Native Build Tools/Native Image | Dependency version, metadata file, build tool và Native Image version |
| Buildpack build cache | Layer được buildpacks dùng trong lúc build image | Cloud Native Buildpacks/Spring Boot plugin | Builder, buildpack, dependency và application inputs |
| Buildpack launch cache | Layer được buildpacks dùng cho image launch | Cloud Native Buildpacks/Spring Boot plugin | Run image, launch layers và buildpack metadata |
| Build workspace | File tạm trong quá trình build image | Spring Boot plugin/Docker daemon | Một lần build hoặc workspace lifecycle |
| Docker/OCI layer cache | Image layers và base images | Docker/OCI engine | Layer content, Dockerfile/build context và image digest |

~~~mermaid
flowchart TB
    S["Source, build scripts, lock files"] --> G["Gradle or Maven"]
    G --> D["Dependency / wrapper cache"]
    G --> B["Build output cache"]
    G --> A["Spring AOT output"]
    A --> R["Reachability metadata + Native Image"]
    R --> N["Native executable"]
    N --> P["Cloud Native Buildpacks"]
    P --> C["Build cache + launch cache"]
    P --> I["OCI image layers"]
~~~

## 3. Cache key phải phản ánh mọi input ảnh hưởng kết quả

Cache chỉ đúng khi hai lần build có cùng input có ý nghĩa và output có thể tái sử dụng an toàn. Trước khi bật cache, hãy xác định những yếu tố có thể làm thay đổi artifact.

Với Spring Boot Native Image, các input thường gồm:

- source code và resource;
- `pom.xml`, parent POM, `settings.gradle(.kts)`, build scripts và convention plugins;
- Maven/Gradle Wrapper và plugin version;
- dependency lock files, version catalog, BOM và dependency constraints;
- JDK vendor/version, compiler toolchain và annotation processors;
- Spring Boot/Spring Framework version và profile dùng cho AOT;
- GraalVM distribution/version, Native Build Tools version và native-image options;
- OS, CPU architecture, libc, compiler, sysroot và native libraries;
- builder image, run image, buildpack order/version và `BP_*` environment;
- các biến cấu hình làm thay đổi generated source hoặc kết quả task.

Gradle và các build-cache extension có thể fingerprint nhiều input tự động. Tuy nhiên, task tùy biến phải khai báo đầy đủ input/output. Nếu task đọc một environment variable nhưng không khai báo nó là input, cache có thể trả kết quả cũ dù môi trường đã đổi.

### 3.1. Phân biệt input ổn định và input dễ thay đổi

| Input | Cách đưa vào cache key |
| --- | --- |
| Wrapper version | Hash file wrapper properties hoặc dùng cache riêng theo wrapper |
| Dependency versions | Hash lock files, version catalog, POM và dependency constraints |
| JDK/GraalVM version | Đưa version/vendor vào key hoặc phân vùng cache |
| OS/architecture/libc | Tách cache theo platform/architecture/ABI khi output phụ thuộc |
| AOT profile/arguments | Khai báo là task input và tách biến thể output |
| Builder/run image | Pin tag bất biến hoặc digest; đưa digest vào build identity |
| Secret/token | Không đưa giá trị bí mật vào key; dùng secret store và loại khỏi cache |
| Commit SHA | Có thể dùng làm cache generation/version, nhưng không thay thế fingerprint input |

Không dùng cache key chỉ dựa trên branch hoặc tên job. Hai commit trên cùng branch có thể khác dependency, JDK hoặc AOT profile. Cũng không đưa timestamp hiện tại vào task input nếu output không phụ thuộc timestamp; input biến động không cần thiết làm giảm cache hit.

### 3.2. Cache key và restore key

Cache key chính xác giúp lấy đúng cache. Restore key dạng prefix có thể lấy một cache gần nhất khi không có exact match. Đây là cách hữu ích với dependency cache vì các artifact đã tải vẫn có thể dùng lại sau khi POM thay đổi.

Với build output, không nên dùng restore prefix tùy tiện để ép lấy artifact cũ. Gradle/Maven build cache phải tự xác minh fingerprint; đừng tự giải nén thư mục output từ một commit khác rồi bỏ qua cơ chế đó.

Cache trong CI thường bất biến theo key. Khi input thay đổi, tạo key mới và để hệ thống lưu entry mới; không cố ghi đè cache cũ bằng nội dung khác.

## 4. Cache cho Gradle

### 4.1. Gradle User Home

Gradle User Home mặc định nằm tại `~/.gradle`. Nó chứa nhiều dữ liệu có thể tái sử dụng:

- Gradle distributions được Wrapper tải về;
- dependency artifacts và module metadata;
- kết quả artifact transforms;
- compiled build scripts và plugin-related state;
- local build cache;
- configuration cache nếu dự án bật tính năng này và cơ chế CI cho phép lưu.

Trên CI runner dùng một lần, lưu Gradle User Home thường giảm đáng kể thời gian tải wrapper và dependency. Không cần tự cache toàn bộ thư mục `build/` của project để đạt mục tiêu này.

### 4.2. Bật task output build cache

Trong `gradle.properties`:

~~~properties
org.gradle.caching=true
~~~

Hoặc chỉ bật cho một lần build:

~~~bash
./gradlew --build-cache clean build
~~~

Gradle dùng task input/output fingerprint để tìm output có thể tái sử dụng. Khi task được khôi phục từ cache, log thường hiển thị `FROM-CACHE`.

Build cache chỉ có ích với task cacheable và có input/output được khai báo đầy đủ. Task tùy biến cần mô tả:

- implementation của task;
- file và property đầu vào;
- classpath/toolchain;
- output files/directories;
- path sensitivity và normalization phù hợp.

Nếu task tạo output không xác định, phụ thuộc đường dẫn tuyệt đối hoặc đọc biến môi trường chưa khai báo, không nên đánh dấu cacheable.

### 4.3. Local và remote build cache

Local build cache phù hợp khi runner hoặc workspace được tái sử dụng. Remote build cache phù hợp khi nhiều agent cần dùng chung output. Ví dụ cấu hình Gradle Groovy DSL:

~~~groovy
buildCache {
    local {
        enabled = true
    }
    remote(HttpBuildCache) {
        url = 'https://gradle-cache.example.internal/cache/'
        credentials {
            username = System.getenv('GRADLE_CACHE_USER')
            password = System.getenv('GRADLE_CACHE_PASSWORD')
        }
        push = System.getenv('CI') == 'true' &&
            System.getenv('GITHUB_REF') == 'refs/heads/main'
    }
}
~~~

Đây là cấu hình minh họa cho remote HTTP cache. Backend cần hỗ trợ giao thức Gradle build cache. Chỉ runner tin cậy trên nhánh chính nên có quyền push; pull request từ fork hoặc nhánh không tin cậy chỉ nên đọc cache công khai/được phép.

### 4.4. Configuration cache là cache khác

Có thể bật Gradle configuration cache:

~~~properties
org.gradle.configuration-cache=true
~~~

Configuration cache lưu kết quả cấu hình build để tránh chạy lại phần cấu hình ở những lần invocation sau. Nó không lưu output của `compileJava`, `test` hoặc native compilation; đó là vai trò của build cache.

Configuration cache có thể chứa thông tin được build logic đọc từ environment hoặc credential. Khi dùng CI để lưu qua nhiều job, kiểm tra hướng dẫn bảo mật của cache provider. Với `gradle/actions/setup-gradle`, nếu muốn cache configuration cache qua job, cung cấp `cache-encryption-key` dạng Base64 theo yêu cầu của action và lưu key trong CI secret. Không cache state có thể chứa credential bằng cơ chế plaintext không được kiểm soát.

## 5. GitHub Actions với Gradle

`gradle/actions/setup-gradle@v6` tự quản lý việc khôi phục/lưu một phần Gradle User Home, bao gồm wrapper distributions, dependency caches và local build cache. Action cũng kiểm tra Gradle Wrapper. Với nhánh không phải nhánh chính, có thể đặt cache ở chế độ chỉ đọc:

~~~yaml
name: Gradle build

on:
  push:
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: '21'

      - uses: gradle/actions/setup-gradle@v6
        with:
          cache-read-only: ${{ github.ref != 'refs/heads/main' }}

      - name: Build and test
        run: ./gradlew --build-cache clean test
~~~

Ví dụ dùng Java 21; thay bằng JDK/GraalVM version mà dự án đã chọn. `cache-read-only` giúp nhánh PR dùng cache sẵn có mà không ghi output vào cache dùng chung. Với build native, runner cần được chuẩn bị GraalVM và toolchain phù hợp; cache Gradle không cài thay các toolchain đó.

Nếu bật configuration cache và muốn chia sẻ nó giữa các job, bổ sung `cache-encryption-key` từ secret theo tài liệu của action. Không in secret ra log hoặc đặt nó trong build scan.

## 6. Cache cho Maven

### 6.1. Maven local repository

Maven local repository mặc định là `~/.m2/repository`. Nó lưu:

- dependency JAR/WAR và POM;
- Maven plugin artifacts;
- parent POM và BOM;
- repository metadata như `maven-metadata.xml`;
- thông tin resolver phục vụ việc kiểm tra artifact đã tải.

Maven kiểm tra local repository trước khi tải artifact từ remote repository. Vì vậy, cache thư mục này phù hợp với runner CI dùng một lần.

Không tự thao tác/chỉnh sửa cấu trúc nội bộ của local repository bằng script. Maven Resolver quản lý locking, origin và metadata; hãy để Maven quản lý nội dung.

### 6.2. Cache dependency bằng setup-java

Ví dụ GitHub Actions:

~~~yaml
name: Maven build

on:
  push:
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: '21'
          cache: maven
          cache-dependency-path: |
            **/pom.xml
            .mvn/wrapper/maven-wrapper.properties
            .mvn/extensions.xml

      - name: Verify
        run: ./mvnw -B verify
~~~

`setup-java` quản lý dependency cache theo OS, kiến trúc, package manager và hash các file dependency được chỉ định. Tùy cấu hình repository, Maven wrapper distribution cũng có cache riêng. Với multi-module project, đưa các POM liên quan vào `cache-dependency-path`.

Không đưa `settings.xml` có token/password vào cache key hoặc cache path. Nếu cấu hình mirror/repository thay đổi, cân nhắc version hóa tên cache hoặc tách runner/cache theo repository identity; credential vẫn phải được cấp từ secret.

### 6.3. SNAPSHOT và metadata động

`SNAPSHOT`, version range và dependency khai báo bằng version động có thể làm kết quả resolve thay đổi theo thời gian dù source không đổi. Maven metadata hỗ trợ tìm version và snapshot timestamp; đây là dữ liệu có thể thay đổi trên remote repository.

Với CI phát hành, ưu tiên:

- version cố định cho dependency và plugin;
- BOM và dependency management được review;
- dependency lock/verification strategy phù hợp;
- kiểm tra snapshot theo lịch hoặc policy rõ ràng;
- không giả định cache cũ chứa snapshot mới nhất.

Khi cần cập nhật snapshot hoặc metadata từ remote, dùng policy Maven phù hợp, chẳng hạn `-U` cho lần kiểm tra cập nhật snapshot/release metadata. Không dùng `-U` cho mọi build nếu không cần vì có thể làm giảm cache hit và tăng truy cập mạng.

### 6.4. Maven Build Cache Extension

Maven local repository chỉ cache artifact đã tải. Nó không tự cache mọi kết quả `compile`, `test` hoặc `package` theo kiểu Gradle task output cache.

Nếu cần tái sử dụng output build, Apache Maven cung cấp Maven Build Cache Extension. Tài liệu hiện hành yêu cầu Maven 3.9.0 trở lên, gồm Maven 4. Extension có thể khai báo trong `.mvn/extensions.xml`:

~~~xml
<extensions>
    <extension>
        <groupId>org.apache.maven.extensions</groupId>
        <artifactId>maven-build-cache-extension</artifactId>
        <version>1.3.0</version>
    </extension>
</extensions>
~~~

Pin version extension theo release đã được dự án kiểm tra. Có thể thêm `.mvn/maven-build-cache-config.xml` để tùy chỉnh file selectors, loại trừ file tạm/môi trường và khai báo tham số plugin quan trọng. Remote cache là tùy chọn và cần backend storage hỗ trợ get/put.

Sau khi bật extension, chạy build bình thường và xem log để xác nhận cache được khởi tạo. Kiểm tra `buildinfo.xml` của module để bảo đảm source files và tham số plugin ảnh hưởng output đã được fingerprint.

Không coi extension này là thay thế Maven local repository. Hai cache phục vụ hai mục tiêu khác nhau:

- `~/.m2/repository`: tránh tải dependency/plugin đã có;
- Maven build cache: tránh chạy lại các phase/plugin execution có output hợp lệ để khôi phục.

## 7. Cache metadata cho Native Image và Spring AOT

### 7.1. Repository metadata và reachability metadata là hai thứ khác nhau

Từ “metadata” có thể chỉ nhiều dữ liệu khác nhau:

| Loại metadata | Ví dụ | Cache ở đâu |
| --- | --- | --- |
| Maven repository metadata | `maven-metadata.xml`, snapshot version mapping | Maven local repository/Resolver |
| Gradle module metadata | POM, `.module`, version/artifact descriptors | Gradle dependency cache |
| Spring AOT output | Generated initializer, source, class và resource | Build output/task cache |
| GraalVM reachability metadata | Reflection, JNI, resource, serialization | Dependency JAR hoặc source resource dưới `META-INF/native-image` |
| Native build metadata | Build arguments, toolchain, target và build report | Artifact/log của build; fingerprint các input liên quan |

Không tạo một thư mục “metadata cache” dùng chung rồi chép metadata của mọi dependency vào đó. Metadata reachability gắn với thư viện và version cụ thể; metadata của một dependency mới có thể thay đổi khi nâng version.

### 7.2. Reachability metadata trong dependency

Native Image có thể đọc `reachability-metadata.json` từ classpath dưới:

~~~text
META-INF/native-image/<groupId>/<artifactId>/reachability-metadata.json
~~~

Metadata có thể nằm trong dependency JAR hoặc trong source resource của ứng dụng. Khi dependency JAR đã được lưu trong Gradle/Maven dependency cache, file metadata bên trong JAR được giữ cùng artifact đó. Cache key dependency/version vì thế cũng xác định metadata đi kèm.

Nếu ứng dụng dùng GraalVM Reachability Metadata Repository thông qua Native Build Tools, plugin có thể tải metadata cần thiết trong quá trình native image generation. Với Gradle, task `collectReachabilityMetadata` có thể tải bản metadata về `build/native-reachability-metadata`. Nếu một bước đóng gói khác cần metadata đó, có thể thêm task output vào JAR theo hướng dẫn plugin:

~~~kotlin
tasks.named("jar") {
    from(tasks.named("collectReachabilityMetadata"))
}
~~~

Chỉ thêm bước này khi pipeline thực sự cần đưa metadata repository vào JAR, ví dụ buildpack hoặc một hệ thống khác sẽ thực hiện Native Image compilation sau đó. Nếu native build được chạy trực tiếp bởi Gradle plugin, không cần đóng gói lại metadata chỉ để tạo thêm một bản sao.

### 7.3. Input nào làm metadata cache mất hiệu lực?

Ít nhất cần xét:

- dependency coordinates và versions;
- GraalVM Native Build Tools version;
- GraalVM/JDK version;
- metadata files do ứng dụng quản lý;
- Native Image options;
- target OS/architecture và ABI nếu metadata/build output phụ thuộc;
- Spring Boot version, AOT output và classpath.

Metadata trong JAR được version hóa cùng dependency. File custom trong `src/main/resources/META-INF/native-image` là source input, nên phải được tính vào source/build fingerprint. Không cache metadata generated của branch khác nếu dependency graph hoặc native build flags khác nhau.

### 7.4. Cache Spring AOT output

Spring AOT tạo generated sources, classes và resources. Các output này phụ thuộc classpath và những điều kiện được đánh giá ở build time. Ví dụ profile hoặc property làm thay đổi bean graph có thể tạo ra output khác.

Hãy dùng cơ chế task/build cache của Gradle/Maven khi task khai báo đầy đủ input. Không cache riêng thư mục generated output chỉ theo source hash. Nếu AOT profile, system property hoặc environment variable ảnh hưởng điều kiện bean mà không nằm trong cache key, build có thể khôi phục initializer không phù hợp.

Với nhiều biến thể AOT, tách output directory hoặc cache namespace theo profile/target. Không cho hai job đồng thời ghi vào cùng generated output directory.

## 8. Cache Cloud Native Buildpacks

### 8.1. Build cache, launch cache và workspace

Spring Boot Maven/Gradle plugin dùng Cloud Native Buildpacks để tạo OCI image. Buildpacks chia ứng dụng thành các layer; cache được quản lý riêng:

| Thành phần | Mục đích | Hành vi |
| --- | --- | --- |
| Build cache | Lưu layer dùng trong quá trình build image | Giúp buildpack tái sử dụng dependency/build layer giữa các lần build |
| Launch cache | Lưu layer liên quan đến quá trình launch image | Được dùng bởi buildpack lifecycle khi tạo/launch image |
| Build workspace | File tạm mà builder/buildpacks dùng trong lúc build | Không phải cache output lâu dài; cần vòng đời workspace riêng |
| OCI image layers | Layer của image được tạo ra | Có thể được container registry/daemon tái sử dụng theo digest |

Đây không phải cùng một cache với Gradle/Maven. Buildpack cache được quản lý bởi lifecycle và buildpack; không nên tự giải nén, sửa hoặc ghép layer thủ công.

### 8.2. Volume name mặc định có thể làm cache mất hiệu lực

Spring Boot plugin mặc định đặt tên cache volume dựa trên full image name. Nếu tag image thay đổi theo version hoặc commit, tên volume cũng có thể thay đổi và cache cũ không được dùng lại.

Đặt tên volume ổn định theo ứng dụng và platform, đồng thời tách cache giữa môi trường không tin cậy và môi trường phát hành:

- tên cache không chứa commit SHA;
- phân vùng theo ứng dụng, architecture và builder/stack khi cần;
- không dùng chung cache có quyền ghi giữa pull request không tin cậy và release pipeline;
- chủ động xóa cache khi builder/stack hoặc format layer không còn tương thích.

### 8.3. Cấu hình Gradle buildpack cache

Ví dụ Kotlin DSL:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

tasks.named<BootBuildImage>("bootBuildImage") {
    imageName.set("registry.example.internal/billing-service:ci")

    buildCache {
        volume {
            name.set("billing-service-linux-amd64.build")
        }
    }
    launchCache {
        volume {
            name.set("billing-service-linux-amd64.launch")
        }
    }
}
~~~

Tên volume ở ví dụ ổn định giữa các commit. Nếu build x86-64 và ARM64, dùng cache volume riêng cho từng kiến trúc. Nếu đổi builder image hoặc stack, cân nhắc đổi cache namespace để tránh tái sử dụng layer không phù hợp.

Nếu runner có Docker daemon dùng một lần, named volume cũng biến mất khi runner bị hủy. Có thể dùng bind mount trên runner có disk bền vững hoặc cấu hình build cache thành OCI image để push/pull qua registry:

~~~kotlin
tasks.named<BootBuildImage>("bootBuildImage") {
    buildCache {
        image {
            name.set("registry.example.internal/cache/billing-service:build")
        }
    }
}
~~~

Spring Boot hỗ trợ build cache image để chia sẻ cache giữa các host. Launch cache và build workspace vẫn có vòng đời riêng; không giả định chỉ cấu hình build cache image là đã lưu mọi dữ liệu buildpack.

### 8.4. Cấu hình Maven buildpack cache

Ví dụ Maven plugin với named volumes:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <image>
            <buildCache>
                <volume>
                    <name>billing-service.build</name>
                </volume>
            </buildCache>
            <launchCache>
                <volume>
                    <name>billing-service.launch</name>
                </volume>
            </launchCache>
        </image>
    </configuration>
</plugin>
~~~

Có thể cấu hình build cache bằng image để chia sẻ giữa host:

~~~xml
<image>
    <buildCache>
        <image>
            <name>registry.example.internal/cache/billing-service:build</name>
        </image>
    </buildCache>
</image>
~~~

Đặt cấu hình này bên trong `<configuration>` của `spring-boot-maven-plugin`. Nếu cần cấu hình cả build cache và launch cache, giữ cả hai block trong cùng phần `<image>`.

### 8.5. Builder, run image và buildpack cũng là input

Buildpack cache không đảm bảo output tương thích nếu builder hoặc buildpack đã thay đổi. Pin:

- builder image theo version hoặc digest;
- run image theo version hoặc digest;
- buildpack order và version;
- buildpack environment variables như `BP_NATIVE_IMAGE`, `BP_JVM_VERSION` và các biến liên quan;
- target architecture và OS;
- Spring Boot plugin version.

Nếu buildpack tạo Native Image, các native compiler flags, GraalVM version, libc và target architecture cũng phải phù hợp. Không tái sử dụng native executable x86-64 cho ARM64 hoặc binary glibc cho musl runtime chỉ vì cache hit.

## 9. GitHub Actions với Maven và buildpack

Ví dụ pipeline Maven có dependency cache và buildpack named volume:

~~~yaml
name: Native image container

on:
  push:
  pull_request:

jobs:
  package:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: '21'
          cache: maven
          cache-dependency-path: |
            **/pom.xml
            .mvn/wrapper/maven-wrapper.properties
            .mvn/extensions.xml

      - name: Build OCI image
        run: ./mvnw -B -Pnative spring-boot:build-image
~~~

Named volumes của buildpack chỉ tồn tại trong vòng đời Docker daemon. Nếu GitHub-hosted runner mới được cấp cho mỗi job, volume không tự chuyển sang runner kế tiếp. Để chia sẻ qua runner, dùng build cache image trong registry hoặc runner tự quản lý có Docker storage bền vững.

Nếu workflow chạy `package` rồi `build-image`, kiểm tra lifecycle để tránh chạy cùng một phase hai lần không cần thiết. `build-image` có thể fork lifecycle để bảo đảm package đã chạy; trong pipeline phức tạp có thể chọn goal phù hợp và cấu hình rõ thứ tự.

## 10. Cache trong pipeline Native Image nhiều giai đoạn

Một pipeline thường có các giai đoạn:

1. Resolve dependencies.
2. Compile và test JVM.
3. Spring AOT processing.
4. Native Image compilation.
5. Build OCI image bằng buildpack.
6. Test container và publish.

Không phải cache nào cũng nên chia sẻ qua mọi giai đoạn:

| Giai đoạn | Cache phù hợp | Điều kiện |
| --- | --- | --- |
| Resolve dependencies | Gradle User Home hoặc Maven local repository | Tách theo OS/tool version/repository trust |
| Compile/test JVM | Gradle build cache hoặc Maven Build Cache Extension | Task output deterministic, input đầy đủ |
| Spring AOT | Task/build cache | Profile, classpath và build-time conditions nằm trong fingerprint |
| Reachability metadata | Dependency cache và task output cache | Dependency/version và GraalVM plugin khớp |
| Native Image compile | Build cache nếu task hỗ trợ và fingerprint đầy đủ; cache tool downloads | Tách OS, architecture, libc, GraalVM và compiler |
| Buildpack | Build/launch cache của CNB | Builder, buildpack, app layers và platform phù hợp |
| Container test | Thường dùng image artifact theo digest | Test đúng image được build; không restore binary cũ |

Với native compilation, không mặc định task có thể được cache an toàn giữa các môi trường khác nhau. Native executable phụ thuộc OS, architecture, libc, compiler và nhiều thành phần của toolchain. Chỉ bật remote output cache khi plugin/task hỗ trợ và đã xác minh output có thể tái sử dụng đúng.

## 11. Bảo mật cache và tính toàn vẹn artifact

Cache có thể chứa executable, class file, generated source, metadata và artifact từ dependency. Một cache bị đầu độc có thể khiến CI chạy output do job không tin cậy tạo ra.

Áp dụng các nguyên tắc:

- chỉ job tin cậy được ghi remote build cache dùng cho release;
- pull request từ fork không được push vào cache chung;
- tách cache theo repository, trust boundary, platform và builder khi cần;
- không cache file chứa credential như Maven `settings.xml`, Docker `config.json` hoặc secret;
- không lưu configuration cache chứa credential nếu chưa mã hóa theo cơ chế được hỗ trợ;
- pin dependency/plugin/builder versions và kiểm tra checksum/signature theo policy;
- giới hạn quyền đọc/ghi remote cache;
- đặt retention/eviction và theo dõi dung lượng;
- khi nghi cache bị nhiễm, đổi namespace/key và rebuild từ nguồn tin cậy.

Không dùng cache như nguồn phát hành cuối cùng. Artifact phát hành cần có provenance, checksum/digest và được tạo bởi pipeline được kiểm soát.

## 12. Đo hiệu quả cache

Cache không tự động làm pipeline nhanh hơn. Cache restore, upload, nén và giải nén cũng tiêu tốn thời gian và network.

Theo dõi:

- cache hit/miss theo từng loại;
- thời gian restore và save;
- dung lượng cache và tỷ lệ eviction;
- số task `FROM-CACHE`;
- thời gian resolve dependency;
- thời gian Spring AOT và Native Image compilation;
- thời gian buildpack lifecycle;
- image layer reuse và image size;
- tổng thời gian pipeline từ checkout tới artifact.

Ví dụ cách đọc:

| Hiện tượng | Ý nghĩa có thể có | Hành động |
| --- | --- | --- |
| Dependency cache hit cao nhưng build vẫn lâu | Compile/test/native compilation chiếm phần lớn thời gian | Xem build output cache và profiling task |
| Gradle build cache miss sau mỗi job | Cache key hoặc task inputs thay đổi; remote cache chưa dùng | Kiểm tra task fingerprint và cache backend |
| Maven tải lại plugin dù dependency cache có | Plugin/version/repository metadata chưa được cache hoặc key không bao phủ file liên quan | Kiểm tra cache path và cache-dependency-path |
| AOT task luôn chạy lại | AOT inputs thay đổi hoặc task chưa cacheable | Kiểm tra profile, arguments và task outputs |
| Buildpack cache miss ở mỗi commit | Cache volume phụ thuộc image tag hoặc daemon ephemeral | Đặt volume ổn định hoặc dùng cache image |
| Cache restore lâu hơn build | Cache quá lớn hoặc hit rate thấp | Giảm phạm vi, chia cache và đo lại |
| Native binary lấy từ cache nhưng lỗi trên runner khác | Cache không phân vùng theo architecture/ABI/toolchain | Tách cache theo target và rebuild |

Đo cả cold build và warm build. Cold build cho biết chi phí thực khi cache rỗng; warm build cho biết hiệu quả sau khi cache được làm nóng. Báo cáo riêng từng giai đoạn thay vì chỉ công bố tổng thời gian.

## 13. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Gradle không có `FROM-CACHE` | Task không cacheable, input thay đổi hoặc build cache chưa bật | Kiểm tra `org.gradle.caching`, task annotations và fingerprint |
| Gradle cache hit nhưng output sai | Task khai báo thiếu input hoặc dùng environment không được fingerprint | Sửa task input/output; vô hiệu cache cho task không deterministic |
| Configuration cache liên tục bị miss | Build logic không tương thích hoặc configuration input thay đổi | Đọc Gradle configuration-cache report và xử lý input |
| Maven tải dependency ở mọi lần chạy | Cache path sai, key không khớp hoặc runner không restore | Kiểm tra `~/.m2/repository` và cấu hình CI |
| Maven Build Cache Extension không hoạt động | Maven version thấp, extension/config thiếu hoặc plugin parameters chưa reconcile | Kiểm tra Maven 3.9+, `.mvn/extensions.xml`, log và `buildinfo.xml` |
| Maven dùng snapshot cũ | Local repository còn snapshot/metadata cũ | Kiểm tra repository policy và chạy update có chủ đích |
| Native Image thiếu metadata sau cache hit | Metadata dependency thay đổi hoặc AOT/native task input chưa đầy đủ | Rebuild từ dependency graph và metadata đúng version |
| Buildpack luôn tạo lại layer | Image name/tag làm thay đổi volume name hoặc daemon không giữ volume | Dùng cache volume ổn định hoặc cache image |
| Buildpack báo cache layer không hợp lệ | Builder/buildpack/stack thay đổi | Tách cache namespace hoặc làm mới cache có kiểm soát |
| Image build được nhưng chạy sai kiến trúc | Cache/native artifact dùng sai platform | Tách cache theo OS/architecture/ABI |
| Cache remote không thể ghi | Job không có quyền push hoặc cache read-only | Kiểm tra branch policy và quyền backend |
| CI cache chứa dữ liệu nhạy cảm | Đã cache nhầm settings/credential/configuration state | Loại file khỏi cache, rotate secret và làm mới cache |

## 14. Quy trình thiết lập cache theo thứ tự

Giả sử dịch vụ billing dùng Gradle, Spring AOT, GraalVM Native Image và `bootBuildImage`.

**Bước 1 — lập danh sách cache**

- Gradle User Home cho wrapper/dependencies.
- Gradle build cache cho task output cacheable.
- Configuration cache nếu build tương thích và có yêu cầu.
- Reachability metadata đi cùng dependency hoặc output task.
- Buildpack build/launch cache.

**Bước 2 — cố định đầu vào**

- Pin Gradle Wrapper, JDK/GraalVM, Spring Boot và Native Build Tools.
- Dùng dependency lock/version catalog.
- Ghi rõ AOT profile và native-image arguments.
- Pin builder/run image và target architecture.

**Bước 3 — bật dependency cache**

Thêm `gradle/actions/setup-gradle@v6` hoặc `setup-java` với Maven cache. Chạy một cold build để làm nóng cache.

**Bước 4 — bật build output cache**

Bật `org.gradle.caching=true` hoặc Maven Build Cache Extension. Kiểm tra task hit/miss và xác minh output sau một lần `clean` build.

**Bước 5 — kiểm tra AOT và reachability metadata**

Xác nhận cache fingerprint có profile, classpath, dependency versions, plugin và Native Image options. Chạy native test để xác nhận metadata được đưa vào executable.

**Bước 6 — bật buildpack cache**

Đặt tên build/launch volume ổn định. Nếu runner ephemeral, dùng build cache image hoặc Docker daemon/storage bền vững.

**Bước 7 — kiểm tra trust boundary**

Chỉ nhánh chính/release pipeline có quyền ghi cache chung. PR không tin cậy chỉ đọc cache được phép.

**Bước 8 — đo cold/warm build**

So sánh thời gian resolve dependency, compile, AOT, native compile và buildpack. Giữ cache chỉ khi tiết kiệm thực tế lớn hơn chi phí restore/save.

## 15. Checklist trước khi đưa cache vào CI

- [ ] Đã phân biệt dependency cache, build output cache, configuration cache và buildpack cache.
- [ ] Gradle Wrapper/Maven Wrapper và JDK/GraalVM version được pin.
- [ ] Cache key phản ánh OS, architecture, build files và dependency lock/version.
- [ ] AOT profile, arguments và build-time conditions là task inputs.
- [ ] Reachability metadata được version hóa cùng dependency hoặc source resource.
- [ ] Không cache generated AOT/native output bằng key chỉ dựa trên branch.
- [ ] Gradle build cache chỉ áp dụng cho task có input/output đầy đủ.
- [ ] Maven local repository được cache riêng với Maven Build Cache Extension.
- [ ] Maven Build Cache Extension chỉ bật khi Maven version và plugin configuration tương thích.
- [ ] Buildpack build cache và launch cache có tên ổn định, tách platform/trust boundary.
- [ ] Runner ephemeral có chiến lược lưu buildpack cache qua registry hoặc storage bền vững.
- [ ] Builder/run image và buildpack versions được pin.
- [ ] Không cache credential, token hoặc cấu hình nhạy cảm ở dạng plaintext.
- [ ] Chỉ runner tin cậy có quyền ghi remote cache.
- [ ] Đã kiểm tra cache hit/miss, restore/save time và artifact correctness.
- [ ] Đã chạy cold build và warm build trên cùng target.
- [ ] Native executable được test trong runtime container cuối.

**Ghi nhớ:** cache đúng là cache theo đúng đầu vào và đúng lớp. Gradle/Maven dependency cache giữ artifact đã tải; build cache giữ output task có fingerprint hợp lệ; Spring AOT và reachability metadata phụ thuộc classpath/profile/toolchain; buildpack cache giữ layer theo lifecycle của builder. Tách cache, pin đầu vào, giới hạn quyền ghi và kiểm chứng output sau cache hit để pipeline nhanh hơn mà vẫn tái lập được.

## Tài liệu tham khảo

- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): task output cache, local/remote build cache và yêu cầu khai báo input/output.
- [Gradle — Gradle on GitHub Actions](https://docs.gradle.org/current/userguide/github-actions.html): `setup-gradle`, Gradle User Home caching và cấu hình cache trong CI.
- [GitHub Actions — actions/setup-java](https://github.com/actions/setup-java): cache dependency Maven/Gradle, wrapper và JDK trong workflow.
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): local/remote repository và offline build.
- [Apache Maven — Maven Build Cache Extension](https://maven.apache.org/extensions/maven-build-cache-extension/): điều kiện Maven version, extension setup, cache config và remote cache.
- [Apache Maven — Repository Metadata](https://maven.apache.org/repositories/metadata.html): `maven-metadata.xml` và version/snapshot metadata.
- [Spring Boot Maven Plugin — Packaging OCI Images](https://docs.spring.io/spring-boot/maven-plugin/build-image.html): buildpack build/launch cache, workspace, volume và cache image.
- [Spring Boot Gradle Plugin — Packaging OCI Images](https://docs.spring.io/spring-boot/gradle-plugin/packaging-oci-image.html): cấu hình `bootBuildImage` cache và Docker daemon.
- [Spring Boot — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/reference/packaging/aot.html): generated AOT code và điều kiện chạy ứng dụng đã xử lý AOT.
- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): metadata reflection, JNI, resource và serialization.
- [GraalVM Native Build Tools — Gradle Plugin](https://graalvm.github.io/native-build-tools/latest/gradle-plugin): tích hợp Native Image, metadata repository và task thu thập metadata.

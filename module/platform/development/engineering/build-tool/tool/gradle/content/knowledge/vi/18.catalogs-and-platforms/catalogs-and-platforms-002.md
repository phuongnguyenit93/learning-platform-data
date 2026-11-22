# Cấu trúc `libs.versions.toml`: `versions`, `libraries`, `bundles` và `plugins`

## 1. Version Catalog giải quyết vấn đề gì?

Trong dự án Gradle Java, bạn có thể viết trực tiếp dependency ở nhiều `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
    testImplementation 'org.junit.jupiter:junit-jupiter-api:5.11.4'
    testRuntimeOnly 'org.junit.jupiter:junit-jupiter-engine:5.11.4'
}
~~~

Khi có nhiều subprojects, việc lặp lại tọa độ và version làm khó bảo trì: dễ đánh sai `group:name`, quên nâng version ở một module, thiếu liên kết giữa plugin và library versions. **Gradle Version Catalog** cho phép đặt danh mục các dependency coordinates, version identifiers, bundles và plugin IDs tại một nơi, rồi truy cập bằng các accessor được Gradle sinh.

File chuẩn của Gradle build là **`gradle/libs.versions.toml`**. Khi file này có đúng vị trí dưới root build, Gradle tự import thành catalog tên **`libs`** và cung cấp type-safe accessors trong project build scripts.

~~~text
gradle/libs.versions.toml
    |
    +-- [versions]  -----> libs.versions.<alias>
    +-- [libraries] -----> libs.<alias>
    +-- [bundles]   -----> libs.bundles.<alias>
    +-- [plugins]   -----> libs.plugins.<alias>
~~~

Các phần có mục đích khác nhau:
- **`[versions]`:** định nghĩa version keys, có thể dùng lại ở nhiều library/plugin aliases.
- **`[libraries]`:** ánh xạ alias đến tọa độ external module (`group:name[:version]`).
- **`[bundles]`:** gom những aliases thuộc `[libraries]` thành một nhóm dependency.
- **`[plugins]`:** khai Gradle plugin ID và version để dùng trong `plugins { alias(...) }`.

**Giới hạn quan trọng:** Version catalog chứa **version được yêu cầu**, không phải khóa version cuối cùng sau conflict resolution. Nó cũng không tự chọn repository, không tự tải artifact, không tự thêm mọi library vào classpath và không thay thế BOM/platform hay dependency locking.

Mục tiêu cuối bài: viết được TOML hợp lệ, dùng đúng alias Groovy DSL, xây một ứng dụng Java 17 và JUnit test từ catalog, phân biệt catalog với platform/BOM và biết chẩn đoán lỗi TOML, version ref, alias, plugin scope.

**Môi trường:** ví dụ dùng Gradle **Groovy DSL** (`build.gradle`/`settings.gradle`), Gradle Wrapper, JDK 17+. Linux/macOS chạy `./gradlew`; Windows PowerShell chạy `.\gradlew.bat`. Các versions minh họa được cố định để dễ kiểm chứng; không được hiểu là phiên bản mới nhất.

## 2. File TOML được nạp ở đâu và khi nào?

Cấu trúc:

~~~text
catalog-lab/
├── settings.gradle
├── build.gradle
├── gradle/
│   ├── libs.versions.toml
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── gradlew
└── gradlew.bat
~~~

`libs.versions.toml` nằm trong **`gradle/` của root build**. Đó là convention quan trọng: nếu đặt `libs.versions.toml` cạnh `build.gradle` hoặc đổi tên `catalog.versions.toml` mà không import rõ ràng, Gradle **không tự tạo đúng catalog `libs`** từ file ấy.

Mẫu tổng hợp:

~~~toml
[versions]
commons = "3.17.0"
junit = "5.11.4"
pluginUpdates = "0.52.0"

[libraries]
commons-lang3 = { module = "org.apache.commons:commons-lang3", version.ref = "commons" }
junit-jupiter-api = { module = "org.junit.jupiter:junit-jupiter-api", version.ref = "junit" }

[bundles]
test-api = ["junit-jupiter-api"]

[plugins]
dependency-updates = { id = "com.github.ben-manes.versions", version.ref = "pluginUpdates" }
~~~

Trong Groovy DSL, một project có thể sử dụng:

~~~groovy
dependencies {
    implementation libs.commons.lang3
    testImplementation libs.bundles.test.api
}
~~~

Để áp plugin alias, dùng **`plugins {}` trong project script**:

~~~groovy
plugins {
    alias(libs.plugins.dependency.updates)
}
~~~

Hai đoạn trên là **snippets minh họa cách dùng catalog**, chưa phải project chạy độc lập: cần plugin để tạo `implementation`/`testImplementation` và repository/Java code tương ứng. Phần 8 cung cấp **project hoàn chỉnh** có thể chạy và kiểm thử.

### 2.1. TOML khác Groovy thế nào?

~~~toml
[versions]
lang = "3.17.0"    # TOML string

[libraries]
commons-lang3 = { group = "org.apache.commons", name = "commons-lang3", version.ref = "lang" }

[bundles]
text = ["commons-lang3"]
~~~

- Section name đứng trong `[ ]`.
- `key = value` dùng để khai báo dữ liệu.
- Object inline có dấu `{ ... }`, các cặp ngăn bởi dấu phẩy.
- List có dấu `[ ... ]`.
- `#` là comment.
- `version.ref = "lang"` là **TOML dotted key**, không phải lệnh chạy Gradle.
- Không đặt lệnh Groovy như `implementation libs.commons.lang3` bên trong TOML.

Gradle đọc file TOML và tạo các type-safe accessors. IDE có thể gợi ý tên alias và phát hiện typo. Nếu TOML sai cú pháp, build có thể thất bại ngay khi configuration, trước khi task Java chạy.

## 3. `[versions]`: đặt tên và dùng lại version

### 3.1. Khai version string

~~~toml
[versions]
commons = "3.17.0"
junit = "5.11.4"
junitPlatform = "1.11.4"
myPlugin = "0.52.0"
~~~

Dòng `junit = "5.11.4"` **không** tự thêm JUnit vào test classpath. Nó tạo một version alias. Các module cụ thể sẽ tham chiếu bằng `version.ref`:

~~~toml
[libraries]
junit-jupiter-api = { module = "org.junit.jupiter:junit-jupiter-api", version.ref = "junit" }
junit-jupiter-engine = { module = "org.junit.jupiter:junit-jupiter-engine", version.ref = "junit" }
~~~

Đổi một `junit` version key sẽ cập nhật các **version requests** của những alias tham chiếu nó. Nhưng khi Gradle chọn selected version cuối cùng, dependency conflicts/constraints/platform vẫn có thể ảnh hưởng.

### 3.2. Required và rich version

Một version string thông thường được Gradle xem là required version (theo ngữ nghĩa constraint), không phải `strictly`. Rich versions có thể khai như sau:

~~~toml
[versions]
stableLine = { strictly = "[3.12,4.0[", prefer = "3.17.0" }

[libraries]
text-core = { module = "org.apache.commons:commons-lang3", version.ref = "stableLine" }
~~~

Các member thường dùng:
- `require`: yêu cầu version hoặc range; Gradle vẫn cần giải các constraints trong graph.
- `strictly`: giới hạn nghiêm ngặt; selected version không được ngoài tập hợp ấy.
- `prefer`: ưu tiên một version khi có thể.
- `reject`: loại các version trong danh sách.
- `rejectAll`: từ chối mọi candidate theo ngữ nghĩa rich version.

Ví dụ khác:

~~~toml
[versions]
safeLine = { require = "[1.4,2.0[", reject = ["1.6.0", "1.6.1"] }
~~~

Đây là ví dụ ngữ pháp constraint, không phải lựa chọn version đề xuất cho một artifact cụ thể. Khi constraints xung đột, Gradle có thể thất bại khi resolve thay vì âm thầm chọn version tùy ý.

**Không dùng `strictly` khắp nơi để “khóa mọi thứ”.** Version locking và platform/BOM có trách nhiệm riêng; strict constraints dùng khi có ranh giới compatibility thật sự cần áp.

### 3.3. Dùng version accessor trong Groovy DSL

Nếu catalog có `commons = "3.17.0"`:

~~~groovy
def requestedVersion = libs.versions.commons.get()
println "Version khai trong catalog: " + requestedVersion
~~~

Kết quả chuỗi ở đây là **version được khai**. Nó không chứng minh `runtimeClasspath` thật sự resolve đúng version ấy: để biết selected version, dùng `dependencyInsight`.

Các accessor version là Provider-based; giữ Provider nếu API tiếp nhận mà không cần resolve ngay. Đừng dùng `.get()` sớm ở top-level chỉ để biến catalog thành một loạt global strings nếu có cách nối lazily.

## 4. `[libraries]`: các cách khai dependency coordinate

### 4.1. Ba biểu diễn cho một module

~~~toml
[libraries]
commons-as-string = "org.apache.commons:commons-lang3:3.17.0"
commons-as-module = { module = "org.apache.commons:commons-lang3", version = "3.17.0" }
commons-as-parts = { group = "org.apache.commons", name = "commons-lang3", version = "3.17.0" }
~~~

Đây là **ba alias cùng trỏ một module**, chỉ để học cú pháp. Trong project thật, nên có một alias rõ ràng, không tạo ba đường truy cập trùng nhau.

Cách khuyên dùng khi version chia sẻ:

~~~toml
[versions]
commons = "3.17.0"

[libraries]
commons-lang3 = { module = "org.apache.commons:commons-lang3", version.ref = "commons" }
~~~

Trên Gradle Groovy DSL:

~~~groovy
repositories {
    mavenCentral()
}

dependencies {
    implementation libs.commons.lang3
}
~~~

Tên `commons-lang3` trong TOML thành `libs.commons.lang3`. Nó cung cấp tọa độ/phiên bản yêu cầu như `implementation 'org.apache.commons:commons-lang3:3.17.0'`, nhưng việc Gradle chọn bản cuối và artifact thực tế vẫn theo cơ chế dependency resolution.

### 4.2. Library alias trả về Provider

`libs.commons.lang3` là kiểu tương đương `Provider<MinimalExternalModuleDependency>`. Bạn có thể dùng cả Groovy DSL:

~~~groovy
dependencies {
    implementation libs.commons.lang3
    // hoặc: implementation(libs.commons.lang3)
}
~~~

Không cần `.get()` để thêm dependency vào `implementation`. Nếu gọi `libs.commons.lang3.get()`, bạn lấy đối tượng dependency được unwrap, **không** có nghĩa Gradle đã tải JAR hoặc resolve tất cả transitive modules.

### 4.3. Library không ghi version

TOML cho phép module không version:

~~~toml
[libraries]
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter" }
~~~

Cấu hình này có ý nghĩa khi version đến từ **BOM/platform hoặc constraint khác**. Nếu không có thông tin nào để chọn version, module có thể resolve lỗi. Catalog không tự đoán latest version.

### 4.4. Những gì không lưu trong `[libraries]`

TOML version catalog chủ ý mô tả module coordinates và versions. Nó **không trực tiếp biểu diễn**:
- Repository URL, credentials, mirrors.
- Exclusion của một transitive module.
- Classifier, artifact type (`@aar`/`@zip`).
- Custom capability selection.
- Local `project(':core')` dependency.
- Java toolchain hoặc compiler flags.
- Task actions hay execution order.

Những nhu cầu trên được cấu hình ở Gradle build script hoặc các plugin/API tương ứng. Nếu cần classifier, Gradle hỗ trợ pattern `variantOf(libs.my.lib) { classifier('...') }` tại nơi khai dependency; không tự viết field `classifier` giả trong TOML.

## 5. `[bundles]`: gom nhiều library aliases

Bundle tạo một **nhóm dependency requests**, không tạo artifact mới:

~~~toml
[versions]
junit = "5.11.4"

[libraries]
junit-jupiter-api = { module = "org.junit.jupiter:junit-jupiter-api", version.ref = "junit" }
junit-jupiter-engine = { module = "org.junit.jupiter:junit-jupiter-engine", version.ref = "junit" }

[bundles]
junit = ["junit-jupiter-api", "junit-jupiter-engine"]
~~~

Groovy DSL:

~~~groovy
dependencies {
    testImplementation libs.bundles.junit
}
~~~

Tương đương thêm hai alias vào cùng một dependency scope:

~~~groovy
dependencies {
    testImplementation libs.junit.jupiter.api
    testImplementation libs.junit.jupiter.engine
}
~~~

**Bundle không:**
- Tạo một JAR hợp nhất.
- Tự trở thành Maven BOM hay Gradle platform.
- Tự ép các versions trong graph, kể cả khi entries có cùng version ref.
- Tự chọn `api`/`implementation`/`runtimeOnly`. Scope bạn truyền bundle vào mới quyết định.
- Tự bật JUnit Platform, đăng ký Test task hoặc áp plugin.
- Chứa các plugin aliases từ `[plugins]` như một library bundle.

Ví dụ thực tế, bundle testing có thể gom các libraries thường dùng cùng nhau; nhưng nếu một module chỉ cần API, gom thêm engine/runtime vào compile classpath không phải lúc nào cũng tối ưu. Đừng biến bundle thành tập “toàn bộ phụ thuộc của công ty”.

### 5.1. Bẫy bundle và BOM

Nếu TOML có aliases `junit-bom` và `junit-jupiter`, bundle gồm cả hai **không tự biến** phần tử BOM thành `platform(libs.junit.bom)`. Gradle chỉ nhận dependency notation do bundle cung cấp. Để BOM thực thi constraints, hãy khai rõ `platform(...)` bên trong dependency declarations.

### 5.2. Kiểu dữ liệu accessor

`libs.bundles.junit` là một Provider cho `ExternalModuleDependencyBundle`. Nó là tập library dependencies; `libs.junit.jupiter.api` là Provider cho một library. Cả hai đều là các abstraction khác với một **resolved file collection** hoặc JAR.

## 6. `[plugins]`: plugin ID và version

Plugin alias thuộc namespace riêng:

~~~toml
[versions]
pluginUpdates = "0.52.0"

[plugins]
dependency-updates = { id = "com.github.ben-manes.versions", version.ref = "pluginUpdates" }
~~~

Trong **`build.gradle` của project**:

~~~groovy
plugins {
    alias(libs.plugins.dependency.updates)
}
~~~

`alias(...)` đưa một plugin requirement vào Gradle **plugins DSL**. Plugin được resolve qua plugin repository (Gradle Plugin Portal hoặc repositories được khai trong `settings.gradle -> pluginManagement.repositories`), không phải do `implementation` của Java app.

- `libs.plugins.dependency.updates` biểu diễn `PluginDependency` qua Provider.
- `libs.commons.lang3` biểu diễn library dependency qua Provider.
- Không đặt `implementation libs.plugins.dependency.updates` để biến Gradle plugin thành library runtime.
- Các core plugins như `java-library` hoặc `application` thường dùng trực tiếp `id 'java-library'`, không cần version alias.

**Lưu ý:** Plugin `com.github.ben-manes.versions` và version `0.52.0` chỉ là ví dụ cú pháp; nếu không cần kiểm tra dependency updates, không bắt buộc cài plugin này. Dự án chạy đầy đủ ở phần 8 không áp plugin cộng đồng.

### 6.1. Root `apply false` và subprojects

Trong một multi-project build, có thể dùng:

**Root `build.gradle` snippet:**

~~~groovy
plugins {
    alias(libs.plugins.dependency.updates) apply false
}
~~~

**Subproject `build.gradle` snippet:**

~~~groovy
plugins {
    alias(libs.plugins.dependency.updates)
}
~~~

`apply false` trong root khai plugin requirement nhưng không áp plugin ngay vào root. Plugin version còn chịu các quy tắc classpath/plugin resolution; đừng trộn version declarations khác nhau ở root/subprojects và buildscript legacy khi chưa có thiết kế rõ.

### 6.2. Catalog plugin alias không dùng trong `settings.gradle`

Gradle không hỗ trợ dùng một `[plugins]` alias được sinh từ version catalog trong **settings file hoặc settings plugin** theo cùng cách với project `plugins {}`. Nếu cần plugin ở settings level, hãy cấu hình `pluginManagement`/settings plugins theo API phù hợp, đừng copy `alias(libs.plugins...)` từ build script rồi mong chạy được.

### 6.3. Plugin version khác library version

Một plugin và library có tên tương tự không tự cùng release train. Dùng một `version.ref` chung chỉ khi tài liệu chính thức của hệ sinh thái yêu cầu. Với plugin aliases, Gradle hiện hành dùng required plugin version; rich plugin version specs kiểu `strictly`/`prefer`/`reject` đã có cảnh báo/deprecation trong tài liệu mới.

## 7. Alias normalization và các lỗi đặt tên

Tên `junit-jupiter-api` trong TOML được chuyển thành accessor `libs.junit.jupiter.api`. Đó là quy tắc thực tế, không phải do plugin Java định nghĩa.

| TOML alias | Type-safe accessor trong Groovy DSL |
| --- | --- |
| `commons-lang3` | `libs.commons.lang3` |
| `junit-jupiter-api` | `libs.junit.jupiter.api` |
| `junit-platform-launcher` | `libs.junit.platform.launcher` |
| `ktor-client-core` | `libs.ktor.client.core` |
| `guava` | `libs.guava` |
| `dependency-updates` trong `[plugins]` | `libs.plugins.dependency.updates` |
| `junit` trong `[bundles]` | `libs.bundles.junit` |
| `commons` trong `[versions]` | `libs.versions.commons` |

Dấu `-` hoặc `_` có thể tạo đường accessor phân cấp; tên dạng camelCase giúp tránh một số subgroup clashes.

### 7.1. Hai alias tạo cùng accessor

Ví dụ hai tên gần giống:

~~~toml
[libraries]
someAlias = { module = "org.example:a", version = "1.0" }
some-alias = { module = "org.example:b", version = "1.0" }
~~~

Gradle có thể báo accessor name clash khi chúng normalize về cùng đường truy cập. Đổi alias thành hai tên rõ ràng như `firstAlias` và `secondAlias`. Đừng chỉ đổi dấu gạch nối mà vẫn tạo cùng accessor.

### 7.2. Parent-child accessor

Ví dụ `[versions]` có cả `jackson` và `jackson-databind`, node `libs.versions.jackson` có thể trở thành subgroup accessor. Tài liệu Gradle cho phép dùng `libs.versions.jackson.asProvider()` để lấy version ở node cha nếu bạn không thể đổi alias. Trong catalog do chính bạn quản lý, tên tránh xung đột thường dễ bảo trì hơn.

### 7.3. Tên reserved

Một số tên như `extensions`, `class` và `convention` là reserved. Với **library alias**, `bundles`, `versions`, `plugins` không được dùng làm first subgroup. Ví dụ `versions-dependency` là tên không hợp lệ; `dependency-versions` hoặc `versionsDependency` là hướng đặt tên khác.

Hãy dùng tên nhất quán, có ý nghĩa (ecosystem + artifact), ví dụ `junit-jupiter-api` và `commons-lang3`, thay vì `util` hoặc `latest`.

## 8. Bài thực hành hoàn chỉnh: Java 17, Commons Lang và JUnit

Bài thực hành này khai cả bốn TOML sections, dùng library alias và bundle trong một ứng dụng Java 17 chạy thật. Plugin alias được **khai nhưng không áp dụng** trong phần chạy chính, vì Java core plugin đủ cho ví dụ.

### 8.1. Cấu trúc dự án

~~~text
gradle-catalog-lab/
├── settings.gradle
├── build.gradle
├── gradle/
│   ├── libs.versions.toml
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── gradlew
├── gradlew.bat
└── src/
    ├── main/java/demo/App.java
    └── test/java/demo/AppTest.java
~~~

Điều kiện: Gradle Wrapper tương thích với Java 17, máy có JDK 17 hoặc toolchain provisioning phù hợp, mạng hoặc cache Maven Central để tải thư viện. Nếu chưa có Wrapper, dùng Gradle đã cài để chạy `gradle wrapper` rồi commit các file Wrapper.

### 8.2. `settings.gradle`

~~~groovy
rootProject.name = 'gradle-catalog-lab'
~~~

Không import TOML thủ công vì Gradle tự phát hiện `gradle/libs.versions.toml`.

### 8.3. `gradle/libs.versions.toml` — toàn bộ

~~~toml
[versions]
commons = "3.17.0"
junit = "5.11.4"
junitPlatform = "1.11.4"
pluginUpdates = "0.52.0"

[libraries]
commons-lang3 = { module = "org.apache.commons:commons-lang3", version.ref = "commons" }

junit-jupiter-api = { module = "org.junit.jupiter:junit-jupiter-api", version.ref = "junit" }
junit-jupiter-engine = { module = "org.junit.jupiter:junit-jupiter-engine", version.ref = "junit" }
junit-platform-launcher = { module = "org.junit.platform:junit-platform-launcher", version.ref = "junitPlatform" }

[bundles]
junit = ["junit-jupiter-api", "junit-jupiter-engine"]

[plugins]
dependency-updates = { id = "com.github.ben-manes.versions", version.ref = "pluginUpdates" }
~~~

Ở đây:
- `commons` được dùng bởi library `commons-lang3`.
- `junit` dùng chung cho Jupiter API và engine.
- `junitPlatform` cấp version Launcher tương thích với JUnit 5.11.4.
- Bundle `junit` dùng hai aliases trong `[libraries]`.
- Plugin alias `dependency-updates` đã tồn tại nhưng **không tự bật plugin**.
- Repository không được khai trong TOML; sẽ có trong `build.gradle`.

### 8.4. `build.gradle` — toàn bộ

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation libs.commons.lang3

    testImplementation libs.bundles.junit
    testRuntimeOnly libs.junit.platform.launcher
}

application {
    mainClass = 'demo.App'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Lý do từng phần:
1. `application` tạo Java project/run task, không cần external plugin.
2. `mavenCentral()` là **nguồn tải** libraries. Catalog không chứa URL.
3. Java toolchain yêu cầu JDK 17.
4. `libs.commons.lang3` thêm Commons Lang vào main classpath.
5. `libs.bundles.junit` thêm Jupiter API và engine vào test dependencies.
6. `libs.junit.platform.launcher` cấp JUnit Platform launcher lúc test runtime.
7. `useJUnitPlatform()` chọn JUnit Platform để thực thi `@Test`.

### 8.5. `src/main/java/demo/App.java`

~~~java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static String message() {
        return "Catalog OK: " + StringUtils.capitalize("gradle");
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

`App.java`/package trùng đường dẫn. `StringUtils.capitalize("gradle")` tạo `"Gradle"`, vì vậy stdout chương trình có thể xác định trước.

### 8.6. `src/test/java/demo/AppTest.java`

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

public final class AppTest {
    @Test
    void messageUsesCatalogDependency() {
        assertEquals("Catalog OK: Gradle", App.message());
    }
}
~~~

Đây là một JUnit 5 test có `@Test` thật, không phải method không được runner phát hiện. `testImplementation` chứa API/engine, `testRuntimeOnly` chứa Launcher, còn Test task được cấu hình JUnit Platform.

### 8.7. Chạy bài thực hành

~~~bash
./gradlew run --quiet
./gradlew test
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency commons-lang3
~~~

**Stdout chính xác của Java application khi `run --quiet` (bỏ qua log khác của Gradle nếu môi trường có):**

~~~text
Catalog OK: Gradle
~~~

`./gradlew test` phải hoàn thành thành công nếu môi trường và thư viện/Gradle tương thích. **Không có stdout từ JUnit test cố định**, vì Gradle hiển thị task states/progress theo phiên bản và có thể báo `UP-TO-DATE`. Muốn xem test report hãy xem output báo cáo do Test task tạo.

`dependencies` cho bạn đồ thị theo **resolvable configuration**, giúp kiểm tra `runtimeClasspath` của app và `testRuntimeClasspath`. `dependencyInsight` cho biết version cuối và nguyên nhân chọn một module, thay vì chỉ nhìn version ref.

### 8.8. Áp dụng plugin alias (mở rộng tùy chọn)

Sau khi chạy lab thành công, thay block `plugins` bằng:

~~~groovy
plugins {
    id 'application'
    alias(libs.plugins.dependency.updates)
}
~~~

Sau đó thử:

~~~bash
./gradlew tasks --all
~~~

Plugin alias mới cần được resolve qua plugin repositories; nếu Plugin Portal hoặc plugin version không truy cập được trong môi trường, bước tùy chọn này có thể thất bại. Nó **không cần thiết** cho Java app và JUnit test của bài lab.

## 9. Một catalog dùng cho nhiều subprojects

Giả sử:

~~~text
multi-project/
├── settings.gradle
├── gradle/libs.versions.toml
├── core/build.gradle
└── app/build.gradle
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'multi-project'
include 'core', 'app'
~~~

Nếu file TOML nằm đúng default location, cả `:core` và `:app` đều có thể dùng `libs`.

**`core/build.gradle` snippet:**

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation libs.commons.lang3
}
~~~

**`app/build.gradle` snippet:**

~~~groovy
plugins {
    id 'application'
}

dependencies {
    implementation project(':core')
    testImplementation libs.bundles.junit
}
~~~

Đây chỉ là snippets giải thích phạm vi catalog; để chạy phải thêm repositories ở phạm vi phù hợp, Java sources và `application.mainClass`.

**Phân biệt:** Catalog dùng chung **tên và coordinates**, không tự thêm Commons Lang vào mọi subproject. Mỗi project quyết định có gọi `api`/`implementation`/`testImplementation` hay không. `api`/`implementation` do Java Library plugin quyết định khả năng lộ dependency sang consumer compile/runtime; catalog không quyết định API exposure.

### 9.1. Dùng repositories tập trung

Trong `settings.gradle` có thể cấu hình:

~~~groovy
import org.gradle.api.initialization.resolve.RepositoriesMode

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}
~~~

Nếu bật `FAIL_ON_PROJECT_REPOS`, không khai `repositories { mavenCentral() }` trong các `build.gradle` dự án vì policy có thể từ chối. Đây là **cơ chế repository management**, không phải một phần của bốn TOML sections.

### 9.2. Không nhầm plugin repository với library repository

- `pluginManagement.repositories` trong settings: nguồn resolve plugin IDs/markers.
- `dependencyResolutionManagement.repositories` hoặc project `repositories`: nguồn resolve libraries.
- `publishing.repositories`: nơi upload artifact, không phải nơi tải dependency cho compilation.

Catalog aliases không thay thế ba phạm vi này.

## 10. Catalog khác BOM/platform: hai cơ chế bổ sung cho nhau

Bối cảnh module là **Catalog và platform**, nên phải phân biệt hai khái niệm:

| Tiêu chí | Version Catalog | BOM / Gradle platform |
| --- | --- | --- |
| Nội dung | Dependency aliases, version requests, bundles, plugin IDs | Constraints/version alignment cho modules |
| Cách dùng | `libs.<alias>`, `libs.bundles.*`, `libs.plugins.*` | `platform(...)`, `enforcedPlatform(...)` |
| Có quyết định selected version chắc chắn? | Không; conflict resolution có thể chọn khác | Constraints tác động resolution; enforced platform có ngữ nghĩa mạnh hơn |
| Có tự mang code vào classpath? | Không; cần declaration trên configuration | Thông thường platform cung cấp constraints, không phải JAR |
| Có gom nhiều libraries? | `[bundles]` gom aliases | BOM quản lý version constraints, không phải bundle các JAR |
| Có là Gradle plugin alias? | Có, `[plugins]` | Không thay thế plugin declaration |

**Catalog là danh bạ. Platform/BOM là tập quy tắc version cho graph. Dependency locking ghi lại selected versions để tăng khả năng tái lập.**

### 10.1. BOM với library alias không có version

Có thể viết TOML:

~~~toml
[versions]
junit = "5.11.4"

[libraries]
junit-bom = { module = "org.junit:junit-bom", version.ref = "junit" }
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter" }
~~~

Trong project có Maven Central:

~~~groovy
dependencies {
    testImplementation platform(libs.junit.bom)
    testImplementation libs.junit.jupiter
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Giải thích:
- `libs.junit.bom` chỉ cung cấp Maven coordinate của BOM; phải dùng `platform(...)` để áp constraints.
- `libs.junit.jupiter` không có version. Khi BOM được import trên cùng dependency resolution context, constraints từ BOM có thể cung cấp version cho module.
- Phần snippet minh họa chưa bao gồm Test launcher nếu Gradle/JUnit setup cần; đây không phải bản thay thế hoàn chỉnh cho lab phần 8.
- Một bundle có chứa `junit-bom` **không tự wrap** dependency ấy bằng `platform(...)`.

### 10.2. Catalog version không ép kết quả conflict resolution

Giả sử trong catalog có `example-core = ...:1.2.0`, nhưng một module khác yêu cầu `...:core:1.5.0`. Gradle có thể chọn `1.5.0` nếu graph constraints/version selection cho phép. Vì vậy `libs.versions.example.get()` chỉ cho biết value được khai, không phải selected version.

Nếu dự án cần reproducibility:
- Chọn BOM/platform constraints khi dependencies đi theo release train.
- Dùng dependency locking khi cần ghi lại resolved versions.
- Dùng rich version constraints khi có version bị cấm hoặc compatibility boundary.
- Dùng dependency verification và repository policy cho trust/integrity.

Không dùng một bundle hoặc một dòng catalog version như lời hứa “mọi machine chắc chắn resolve đúng version đó”.

## 11. Nâng cấp versions và cách kiểm tra thực tế

Một thay đổi version catalog cần xét cả ảnh hưởng compile/runtime/test:

1. Kiểm tra phiên bản mới tương thích Gradle Wrapper, JDK và plugin ecosystem.
2. Đổi đúng một `[versions]` key, hoặc version trong library alias.
3. Chạy `./gradlew test` và các integration tasks của dự án.
4. Xem `dependencies` / `dependencyInsight` của configuration liên quan.
5. Nếu dùng locks, cập nhật lock state theo quy trình của build.
6. Kiểm tra runtime behavior và release notes trước khi phát hành.

**Đừng chỉ sửa phiên bản trong TOML rồi kết luận đã nâng dependency.** Nếu library alias không được một project sử dụng, nó không ảnh hưởng classpath. Nếu selected version do platform/constraint mạnh hơn quyết định, kết quả cũng có thể khác version trong TOML.

## 12. Đặt catalogs khác ngoài file mặc định

Một build có thể có nhiều version catalogs theo mục đích, nhưng phần lớn dự án nên bắt đầu với **một `libs.versions.toml`** để tránh số lượng accessors/versions bị phân tán.

Giả sử:

~~~text
gradle/
├── libs.versions.toml
├── tools.versions.toml
└── test-libs.versions.toml
~~~

Trong **`settings.gradle`**:

~~~groovy
dependencyResolutionManagement {
    versionCatalogs {
        create('tools') {
            from(files('gradle/tools.versions.toml'))
        }
        create('testLibs') {
            from(files('gradle/test-libs.versions.toml'))
        }
    }
}
~~~

Kết quả có thêm `tools` và `testLibs` accessors trong các project; `libs` mặc định vẫn đến từ file default.

**Lỗi:** gọi `from(...)` hai lần cho cùng catalog. Một `VersionCatalogBuilder` chỉ nhận một nguồn import bằng `from(...)`. Muốn bổ sung dữ liệu, dùng method builder như `version(...)`, `library(...)` hoặc một catalog khác, không gộp hai `from` vào cùng catalog.

Ví dụ override version sau import:

~~~groovy
dependencyResolutionManagement {
    versionCatalogs {
        create('sharedLibs') {
            from(files('gradle/shared.versions.toml'))
            version('commons', '3.17.0')
        }
    }
}
~~~

Snippet này cần file `gradle/shared.versions.toml` tồn tại và catalog đó chứa alias/ref có ý nghĩa. Project sẽ gọi `sharedLibs.<alias>`, không tự đổi thành `libs.<alias>`.

### 12.1. `buildSrc` là build riêng

`buildSrc` **không tự kế thừa** catalog của main build. Nếu muốn dùng `libs` trong `buildSrc/build.gradle`, import tại `buildSrc/settings.gradle`:

~~~groovy
dependencyResolutionManagement {
    versionCatalogs {
        create('libs') {
            from(files('../gradle/libs.versions.toml'))
        }
    }
}
~~~

Đường dẫn tương đối ở ví dụ giả định `buildSrc/` nằm cạnh `gradle/` tại root. Nếu cấu trúc khác, phải điều chỉnh. Included builds cũng có catalog/settings context riêng.

Trong **precompiled script plugins** thuộc buildSrc, không thể luôn gọi trực tiếp `alias(libs.plugins.somePlugin)` trong `plugins {}` như ở normal project; build logic có những quy tắc plugin classpath riêng. Hãy đọc tài liệu build logic khi triển khai convention plugins.

## 13. Công dụng nâng cao và giới hạn của TOML

### 13.1. Classifier

Trong TOML:

~~~toml
[libraries]
my-lib = { module = "com.example:my-lib", version = "1.0.0" }
~~~

Nếu cần classifier của một module, ví dụ artifact native:

~~~groovy
dependencies {
    implementation(variantOf(libs.my.lib) {
        classifier('linux-x86_64')
    })
}
~~~

Đây là snippet minh họa; yêu cầu artifact có classifier thật trên repository. Không tự thêm `classifier = ...` vào `[libraries]` vì catalog không hỗ trợ field ấy. Với Gradle Module Metadata variant-aware, cân nhắc chọn variant bằng attributes/capabilities thay vì classifier khi phù hợp.

### 13.2. Excluding transitive dependency

~~~groovy
dependencies {
    implementation(libs.commons.lang3) {
        exclude group: 'org.example', module: 'legacy-helper'
    }
}
~~~

Đây chỉ minh họa syntax exclude, **không khẳng định Commons Lang thực sự kéo module `legacy-helper`**. Exclusion thuộc dependency declaration, không phải TOML library alias. Chỉ exclude sau khi kiểm tra graph, tránh runtime failure vì bỏ một dependency cần thiết.

### 13.3. Không lưu secrets

Version catalog thường được commit lên Git. Đừng lưu repository password, API key, signing key hoặc token CI trong TOML. Những dữ liệu đó thuộc Gradle credentials APIs/Provider/env/secret store với quyền truy cập thích hợp.

### 13.4. Không dùng catalog như policy bảo mật

Catalog không tự xác thực artifact checksum/signature, không cấm repository không tin cậy và không đảm bảo transitive dependencies an toàn. Kết hợp với dependency verification, repository content filtering, dependency locking và CI tests nếu dự án có yêu cầu supply-chain security.

## 14. Chẩn đoán lỗi version catalog

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `libs` không tồn tại | File sai đường dẫn hoặc build logic thuộc build riêng | Dùng `gradle/libs.versions.toml`; import riêng ở buildSrc |
| Không có `libs.commons.lang3` | Alias TOML không phải `commons-lang3` hoặc accessor mismatch | Đọc alias và quy tắc normalize |
| `version.ref` trỏ khóa không tồn tại | Thiếu `[versions]` key | Khai version key hoặc sửa ref |
| Bundle báo thiếu alias | `[bundles]` tham chiếu tên không có trong `[libraries]` | Sửa danh sách aliases |
| Plugin alias không resolve | ID/version hoặc `pluginManagement.repositories` sai | Kiểm tra plugin marker và plugin repositories |
| Dùng plugin alias trong settings báo lỗi | Catalog plugin aliases không dùng như project plugins tại settings | Dùng settings/pluginManagement API phù hợp |
| `libs.versions.*` in A nhưng dependency graph chọn B | Catalog chỉ định requested version; conflict/constraints chọn khác | Kiểm tra `dependencyInsight` |
| Bundle không chạy JUnit 5 | Chưa có engine/launcher hoặc `useJUnitPlatform()` | Khai đủ test deps và test task |
| Versionless module không resolve | Không có BOM/platform hoặc constraint | Thêm version hoặc import platform |
| TOML duplicate key | Hai aliases cùng key trong một section | Đổi tên/hợp nhất |
| Accessor name clash | Hai aliases normalize thành một đường | Chọn tên khác thực sự |
| Reserved alias name | `class`, `extensions`, `convention`, first subgroup `versions`/`bundles`/`plugins` | Đổi tên hợp lệ |
| `from(...)` dùng nhiều lần | Một catalog builder chỉ nhận một import source | Dùng một source hoặc nhiều catalogs |
| `libs` không có ở `buildSrc` | Build khác scope | Import ở `buildSrc/settings.gradle` |
| Thêm library alias nhưng compiler không thấy class | Chưa dùng `implementation`/`api` trong project, hoặc thiếu repo | Thêm dependency declaration và repository |
| TOML có `plugins` nhưng plugin không được áp dụng | Khai trong catalog không đồng nghĩa áp dụng plugin | Gọi `alias(libs.plugins...)` trong `plugins {}` của project |

### 14.1. Bộ lệnh kiểm chứng

~~~bash
./gradlew help
./gradlew tasks --all
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency commons-lang3
./gradlew test --info
~~~

- `help` là kiểm tra nhanh lỗi parse TOML/alias/accessor khi Gradle cấu hình build.
- `dependencies` hiển thị graph của configuration được yêu cầu, không phải JAR list cố định cho mọi task.
- `dependencyInsight` cho selected versions và các lý do resolution.
- `--info` giúp chẩn đoán nhưng có thể chứa thông tin môi trường; tránh chia sẻ logs chứa credentials.

**Quy trình sửa:** kiểm tra file path → TOML syntax → section của alias → accessor mapping → repository scope → selected version → task/test runtime. Không xóa Gradle caches như phản xạ đầu tiên: điều đó không sửa alias/`version.ref` sai.

## 15. Bài tập có đáp án

### Bài 1 — Nhớ bốn sections

Hỏi: `[versions]`, `[libraries]`, `[bundles]`, `[plugins]` dùng cho những dữ liệu nào?

**Đáp án:** Version keys/rich constraints; module coordinates; nhóm library aliases; Gradle plugin IDs/versions.

### Bài 2 — Tên accessor

TOML có `commons-lang3` và `junit-jupiter-api` trong `[libraries]`. Cách gọi ở Groovy DSL?

**Đáp án:** `libs.commons.lang3` và `libs.junit.jupiter.api`.

### Bài 3 — Ref sai

~~~toml
[versions]
jupiter = "5.11.4"

[libraries]
junit-api = { module = "org.junit.jupiter:junit-jupiter-api", version.ref = "junit" }
~~~

**Đáp án:** `version.ref` trỏ đến `junit` nhưng chỉ có `jupiter`. Sửa version key hoặc ref.

### Bài 4 — Bundle là gì?

`[bundles] junit = ["junit-jupiter-api", "junit-jupiter-engine"]` có tải một artifact `junit-bundle.jar` không?

**Đáp án:** Không. Nó thêm hai dependency declarations khi dùng `libs.bundles.junit` trên một configuration. Nó không phải JAR hoặc BOM.

### Bài 5 — Plugin alias

Có `[plugins] dependency-updates = ...`. Dùng ở đâu?

**Đáp án:** `plugins { alias(libs.plugins.dependency.updates) }` trong project `build.gradle`. Không dùng như `implementation libs.plugins...` hoặc mặc định trong settings plugin.

### Bài 6 — Java runtime

Dựa trên lab, lệnh `./gradlew run --quiet` in gì?

**Đáp án:** `Catalog OK: Gradle`. App dùng Commons Lang qua `libs.commons.lang3`. Test kiểm tra chuỗi đó qua JUnit.

### Bài 7 — Platform vs catalog

Có `libs.junit.bom` (BOM coordinate) và `libs.junit.jupiter` (versionless). Muốn dùng version constraints của BOM, viết gì?

**Đáp án:** `testImplementation platform(libs.junit.bom)` rồi `testImplementation libs.junit.jupiter` trong configuration phù hợp.

### Bài 8 — Catalog được chia sẻ như thế nào?

Root có `gradle/libs.versions.toml`, hai subprojects `:app` và `:core`. Chúng có tự thêm mọi library trong catalog không?

**Đáp án:** Không. Cả hai có accessors `libs` nhưng chỉ module nào khai `implementation`/`api`/`testImplementation` thì dependency đó mới tham gia graph.

### Bài 9 — buildSrc

Vì sao `buildSrc/build.gradle` không thấy `libs` dù root project thấy?

**Đáp án:** buildSrc là build riêng; cần import TOML vào `buildSrc/settings.gradle`.

### Bài 10 — Version khác

Catalog yêu cầu `commons-lang3:3.17.0` nhưng `runtimeClasspath` báo selected version khác. Có phải Gradle bỏ qua TOML?

**Đáp án:** Không nhất thiết. TOML đã tạo version request; dependency graph conflicts/platform/constraints có thể chọn version khác. Dùng `dependencyInsight` kiểm chứng.

### Bài 11 — Plugin chưa được tải

`[plugins]` khai một alias nhưng `build.gradle` chỉ có `plugins { id 'application' }`. Plugin ngoài có được áp tự động không?

**Đáp án:** Không. Khai alias chỉ tạo danh mục; phải gọi `alias(libs.plugins.<alias>)` ở project script tương ứng.

### Bài 12 — Một bài tự làm

Hãy thêm một library `guava` vào `[libraries]` và chọn version có sẵn trên Maven Central. Dùng `implementation libs.guava` để thêm dependency, chạy `dependencies --configuration runtimeClasspath`, rồi giải thích vì sao selected version có thể khác version bạn vừa nhập nếu graph có constraint cạnh tranh.

**Tiêu chí đạt:** Bạn tạo được TOML đủ bốn sections, dùng library/bundle/plugin aliases đúng chỗ, tự chạy Java 17/JUnit lab, giải thích requested vs selected versions và hiểu khi nào phải kết hợp BOM/platform/locking.

## 16. Checklist áp dụng

- [ ] `gradle/libs.versions.toml` nằm đúng root Gradle build.
- [ ] TOML có sections hợp lệ, aliases duy nhất, version refs trỏ đúng khóa.
- [ ] Các library aliases phản ánh đúng group:name.
- [ ] Bundle chỉ chứa library aliases có ý nghĩa dùng cùng nhau.
- [ ] Plugin aliases chứa plugin IDs/versions, dùng ở đúng project `plugins {}`.
- [ ] Có repositories thực tế cho project dependencies và plugin resolution.
- [ ] Không nhầm `api`/`implementation`/`testImplementation` với catalog sections.
- [ ] Không coi catalog version là enforced selected version.
- [ ] BOM được import bằng `platform(...)`, không kỳ vọng bundle tự làm BOM.
- [ ] Không dùng rich strict versions nếu chưa xác định compatibility policy.
- [ ] buildSrc/included builds nhận catalog riêng khi cần.
- [ ] Không lưu credentials/token trong catalog.
- [ ] Chạy Gradle `help`, `run`, `test` và dependencyInsight sau khi đổi versions.

## 17. Tài liệu chính thức

- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html): TOML sections, aliases/accessors, rich versions, bundles, plugins và import.
- [Gradle — Troubleshoot Version Catalog Problems](https://docs.gradle.org/current/userguide/how_to_fix_version_catalog_problems.html): reserved names, clashes và lỗi catalog.
- [Gradle — Dependency Management Basics](https://docs.gradle.org/current/userguide/dependency_management_basics.html): module coordinates, repositories và version catalog.
- [Gradle — Platforms](https://docs.gradle.org/current/userguide/platforms.html): BOM/platform constraints, khác bundle.
- [Gradle — Centralizing Repository Declarations](https://docs.gradle.org/current/userguide/centralizing_repositories.html): dependencyResolutionManagement và repositories mode.
- [Gradle — Declaring Dependency Versions](https://docs.gradle.org/current/userguide/declaring_dependency_versions.html): rich versions, conflicts/constraints.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): kiểm soát resolved versions.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): artifact verification.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): dependency reports, dependencyInsight.
- [Gradle — Working with Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html): plugin IDs, pluginManagement và plugin resolution.

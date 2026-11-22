# Phân biệt catalog, platform, dependency locking và convention plugin trong Gradle

## 1. Bốn công cụ không thay thế cho nhau

Một dự án Java dùng Gradle có thể có hàng chục module, hàng trăm dependency, nhiều môi trường CI và các quy tắc biên dịch/kiểm thử thống nhất. Khi đó, bốn công cụ thường được đặt cạnh nhau:

- **Version catalog:** định nghĩa **tên gọi/alias** cho thư viện, plugin và version requests để các project khai báo nhất quán.
- **Dependency platform:** cung cấp **version constraints** cho các module tham gia resolution, giúp các consumer thống nhất những lựa chọn tương thích.
- **Dependency locking:** ghi lại **những version thực sự đã được resolve** ở các configuration được khóa để các lần build có cơ sở tái lập.
- **Convention plugin:** đóng gói **logic cấu hình Gradle dùng chung** như Java 17 toolchain, compiler options, test framework hoặc việc áp dụng các plugin khác.

Bốn câu hỏi tương ứng:

1. Tôi khai báo `commons-lang3`, `junit-jupiter` hoặc plugin bằng tên nào cho dễ quản lý? → **Catalog**.
2. Khi các dependency đòi phiên bản khác nhau, nhóm muốn sử dụng constraints nào? → **Platform**.
3. Hôm nay Gradle đã chọn những version nào, làm sao CI ngày mai giữ graph đó? → **Locking**.
4. Làm sao tất cả project Java cùng biên dịch với JDK 17 và chạy test qua JUnit Platform? → **Convention plugin**.

```text
gradle/libs.versions.toml
         |
         v
implementation(libs.commons.lang3)    (version request / alias)
         |
         +--- platform(project(":platform"))
         |           |
         |           +--- version constraints
         |
         +--- id("java17-conventions")
         |           |
         |           +--- Java toolchain, test, compiler task rules
         |
         v
Gradle dependency resolution
         |
         +--- metadata + constraints + variants + conflicts
         |
         v
resolved dependency graph
         |
         +--- dependency locking -> gradle.lockfile
         |
         v
compileJava / test / run
```

**Không nên hiểu sai:** một catalog không tự làm mọi version trở thành “khóa cứng”; một platform không tự tải mọi thư viện được nhắc trong constraints; một lockfile không tự chứng minh artifact an toàn; một convention plugin không tự có khả năng quản lý version trừ khi tác giả viết logic đó.

## 2. Bảng so sánh mục tiêu, phạm vi, giới hạn

| Tiêu chí | Version catalog | Dependency platform | Dependency locking | Convention plugin |
| --- | --- | --- | --- | --- |
| Câu hỏi chính | Dùng alias nào cho dependency/plugin? | Constraints phiên bản nào tham gia resolution? | Giữ resolved versions nào? | Dùng quy tắc build chung nào? |
| Cấu hình tiêu biểu | `gradle/libs.versions.toml` | Plugin `java-platform`, Maven BOM | `dependencyLocking`, `gradle.lockfile` | Precompiled script/binary plugin |
| Đầu ra chính | Typed accessors và dependency requests | Metadata version constraints | Lock state của graph đã resolve | Các plugin, task, extension/configuration được thiết lập |
| Version trong file có quyết định tuyệt đối? | Không | Không với regular platform constraints | Ghi lại version resolved để đối chiếu | Không phải cơ chế version riêng |
| Tự đưa thư viện vào classpath? | Không | Không; consumer còn phải yêu cầu module | Không | Chỉ nếu plugin chủ động khai báo dependency |
| Tự đặt Java toolchain/test framework? | Không | Không | Không | Có thể |
| Phạm vi mặc định | Build dùng catalog ấy | Consumer import platform | Configurations bật locking và đã resolve | Project áp dụng plugin |
| Gắn với repository Maven? | Alias không thay repository | Platform có thể là project hoặc module được publish | Lock không thay repository/cache | Plugin có thể cấu hình repository khi cần |
| Hỗ trợ CI tái lập? | Giúp chuẩn hóa declarations | Giúp nhất quán constraints | Giữ kết quả đã chọn | Chuẩn hóa build logic |
| Thay dependency verification? | Không | Không | Không | Không |

Ghi nhớ bằng một câu: **catalog đặt tên; platform ràng buộc; locking giữ kết quả; convention plugin chuẩn hóa cách chạy build**.

## 3. Version catalog: tên, module, version và bundle

Gradle thường tự nhận file `gradle/libs.versions.toml` và tạo catalog mặc định tên `libs` cho các project trong main build. Ví dụ:

```toml
[versions]
junit = "5.10.2"
junit-platform = "1.10.2"

[libraries]
commons-lang3 = { module = "org.apache.commons:commons-lang3", version = "3.14.0" }
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }
junit-platform-launcher = { module = "org.junit.platform:junit-platform-launcher", version.ref = "junit-platform" }

[bundles]
junit-testing = ["junit-jupiter", "junit-platform-launcher"]
```

Kotlin DSL trong một project Java:

```kotlin
dependencies {
    implementation(libs.commons.lang3)
    testImplementation(libs.junit.jupiter)
    testRuntimeOnly(libs.junit.platform.launcher)
}
```

TOML có ba tầng:

- **`[versions]`**: nhãn version dùng lại bằng `version.ref`.
- **`[libraries]`**: alias ánh xạ tới tọa độ module và có thể kèm version.
- **`[bundles]`**: nhóm nhiều library aliases thành một tên chung.

Catalog còn có `[plugins]` để khai báo plugin aliases, ví dụ:

```toml
[plugins]
spotless = { id = "com.diffplug.spotless", version = "6.25.0" }
```

Và một project có plugin/repository phù hợp có thể sử dụng:

```kotlin
plugins {
    alias(libs.plugins.spotless)
}
```

Đoạn Spotless là **minh họa riêng** chứ không phải thành phần bắt buộc của project Java 17 ở phần thực hành. Plugin alias không tự tạo plugin repository; plugin ngoài phải resolve được bằng cấu hình `pluginManagement.repositories` thích hợp.

### 3.1. Catalog chỉ tạo request, không chốt version resolved

Ví dụ alias:

```toml
[libraries]
commons-lang3 = { module = "org.apache.commons:commons-lang3", version = "3.12.0" }
```

và project khai báo `implementation(libs.commons.lang3)`. Gradle nhận một request version `3.12.0`. Nếu graph còn yêu cầu `3.14.0` hoặc platform constraint phù hợp, kết quả có thể được chọn thành `3.14.0` theo conflict resolution.

Bởi vậy **requested version khác resolved version**. Catalog không tự ngăn các transitive dependencies đưa yêu cầu version khác vào graph, không áp dụng tự động `strictly`, và cũng không thay thế dependency locking.

Lệnh kiểm chứng trong project Java thích hợp:

```bash
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
```

Khi dùng multi-project, nên gọi đúng project:

```bash
./gradlew :app:dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
```

Đọc output để biết requested và selected version thay vì chỉ nhìn TOML.

### 3.2. Alias có thể không khai báo version

Nếu version do một platform quản lý, alias chỉ cần module:

```toml
[libraries]
commons-lang3 = { module = "org.apache.commons:commons-lang3" }
```

Kotlin DSL vẫn là:

```kotlin
dependencies {
    implementation(libs.commons.lang3)
}
```

Nhưng build phải có **một nguồn version information thích hợp** từ platform, constraint hoặc yêu cầu khác trong graph. Không có nguồn nào quy định version, resolution module có thể thất bại. Việc alias thiếu version là **lựa chọn thiết kế**, không tự luôn đúng hoặc luôn sai.

### 3.3. Alias không phải tọa độ thật

Nếu đổi `commons-lang3` thành `text-utils` trong TOML và dùng `libs.text.utils`, thư viện vẫn có tọa độ `org.apache.commons:commons-lang3`. Đổi alias không đổi package Java, tên JAR được publish hoặc dependency graph nếu module/version thực không đổi.

### 3.4. Catalog trong included builds

Khi có `includeBuild("build-logic")`, build-logic là một **build độc lập với settings riêng**. Đừng cho rằng accessor `libs` của main build tự xuất hiện trong included build. Nếu build-logic cần catalog, phải chủ động định nghĩa/import nó trong settings của included build hoặc thiết kế cách cung cấp dữ liệu phù hợp.

Trong ví dụ chính, convention plugin sẽ **không dùng `libs`**, nên không có phụ thuộc vào catalog root trong code build-logic.

## 4. Dependency platform: một tập version constraints

Platform khác catalog vì nó tham gia **Gradle version resolution**. Có hai dạng phổ biến:

- **Local Java platform project** áp dụng plugin `java-platform`, công bố constraints.
- **External BOM/platform** đã phát hành ở Maven repository, được import qua `platform("group:artifact:version")`.

Platform không phải nơi liệt kê những dependency mà app chắc chắn sẽ sử dụng. Nó cung cấp constraints khi những module đó được yêu cầu trong graph.

### 4.1. Local `java-platform`

Trong project `:platform`, file `platform/build.gradle.kts`:

```kotlin
plugins {
    id("java-platform")
}

dependencies {
    constraints {
        api("org.apache.commons:commons-lang3:3.14.0")
    }
}
```

Consumer:

```kotlin
dependencies {
    implementation(platform(project(":platform")))
    implementation("org.apache.commons:commons-lang3")
}
```

Các constraints từ project `:platform` tham gia resolution của consumer đã import. Dòng `implementation("org.apache.commons:commons-lang3")` vẫn quan trọng: platform **không tự thêm toàn bộ module được nhắc tới**.

Nếu app dùng catalog alias không version, có thể viết:

```kotlin
dependencies {
    implementation(platform(project(":platform")))
    implementation(libs.commons.lang3)
}
```

Đó là cách kết hợp được dùng ở project thực hành.

### 4.2. Regular platform không phải ép version tuyệt đối

Ví dụ một platform có constraint version `3.14.0`; project hoặc dependency khác yêu cầu một version khác. Gradle cần xem toàn bộ version selectors, constraints, attributes và các quy tắc conflict resolution để chọn kết quả.

Đừng ghi nhớ “platform luôn thắng” hoặc “catalog luôn thắng” như quy luật. **Regular platform** giúp thêm ràng buộc/đề xuất phù hợp vào resolution, không phải câu lệnh bất chấp mọi version requirement.

Có các mức version constraint mạnh hơn:

```kotlin
dependencies {
    constraints {
        api("org.apache.commons:commons-lang3") {
            version {
                strictly("3.14.0")
            }
        }
    }
}
```

Đây là **phương án thay thế** cho constraint đơn giản ở platform, không phải code bắt buộc phải đặt thêm. Strict version có thể dẫn đến resolution failure khi không tương thích với graph khác.

### 4.3. `platform` và `enforcedPlatform`

| Cú pháp | Ý nghĩa | Cần chú ý |
| --- | --- | --- |
| `platform(project(":platform"))` | Import constraints của local platform | Kết quả còn chịu version resolution chung |
| `platform("group:bom:version")` | Import BOM hoặc platform đã publish | Cần repository và BOM phù hợp |
| `enforcedPlatform(...)` | Import constraints với semantics mang tính áp đặt mạnh hơn | Có thể ép transitive consumers; đặc biệt cẩn thận với thư viện được publish |

Dùng `enforcedPlatform` một cách tùy tiện để “giải quyết mọi xung đột version” có thể ép consumer khác vào versions không phù hợp. Với Java libraries, regular platform và constraints được thiết kế rõ thường là lựa chọn lành mạnh hơn.

### 4.4. Maven BOM

Ví dụ một project có thể import BOM đã được phát hành:

```kotlin
dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:3.3.4"))
}
```

Đây chỉ minh họa cách import một BOM; project Java 17 ở mục 7 **không cần Spring Boot**. BOM mô tả version dependency management, không tự đưa mọi dependency tương ứng vào classpath, cũng không tự áp dụng plugin Spring Boot.

## 5. Dependency locking: lưu graph resolved có kiểm soát

Catalog và platform chủ yếu cung cấp **input cho resolution**. Locking lưu lại **những module versions đã được Gradle chọn** trong các configurations được quản lý.

Trong `app/build.gradle.kts`:

```kotlin
dependencyLocking {
    lockAllConfigurations()
}
```

Dòng này bật chế độ locking, **không tự tạo lockfile đầy đủ ngay lập tức**. Cần resolve những configuration mục tiêu bằng lệnh có bật ghi lock:

```bash
./gradlew :app:test :app:run --write-locks
```

Với layout Gradle phổ biến, kết quả sẽ tạo/cập nhật file:

```text
app/gradle.lockfile
```

Lockfile chứa metadata phiên bản được resolve cho các configuration đã được đưa vào quá trình ghi. Tùy graph, nó có thể liệt kê cả dependency bắc cầu, không chỉ module khai báo trực tiếp trong app.

Mô hình:

```text
Catalog alias / version request
             + Platform constraints
             + Transitive metadata
             + Resolution rules
                        |
                        v
               resolved dependencies
                        |
               --write-locks
                        v
                gradle.lockfile
                        |
             Lần build kế tiếp
                        |
                        v
          đối chiếu resolution với lock state
```

### 5.1. Locking không thay thế catalog hoặc platform

- Catalog giúp đọc/viết declarations dễ nhất quán.
- Platform giúp constraints có ý nghĩa trong version resolution.
- Lockfile giữ **kết quả được chọn** sau các cơ chế trên.

Bạn có thể dùng locking mà không có catalog, hoặc dùng catalog/platform mà chưa locking. Nhưng với CI cần tái lập, lockfile được quản lý bằng version control thường có giá trị bổ sung lớn.

### 5.2. Lock theo configuration

`lockAllConfigurations()` bật chính sách rộng cho các configurations của project. Nhưng một configuration chưa được resolve **không tự có bản ghi lock** chỉ vì gọi phương thức này. Nếu muốn cấu hình riêng:

```kotlin
configurations.named("runtimeClasspath") {
    resolutionStrategy.activateDependencyLocking()
}
```

Đây là một mảnh mã đặt trong project đã áp dụng Java plugin hoặc plugin tạo `runtimeClasspath`. Không dán đồng thời nhiều chiến lược locking mà không có mục đích rõ.

Một ứng dụng có `compileClasspath`, `runtimeClasspath`, `testCompileClasspath` và `testRuntimeClasspath`; chúng có thể có dependency graphs khác nhau. Việc tạo lock cần resolve đầy đủ những configurations mà tổ chức muốn quản lý.

### 5.3. Cập nhật lock khi nâng version

Quy trình an toàn:

1. Sửa version catalog, platform constraints hoặc dependency declaration theo thay đổi đã review.
2. Chạy những tasks hoặc configurations cần được resolve với `--write-locks`.
3. Đọc diff của `gradle.lockfile`.
4. Chạy compile/test/integration test phù hợp.
5. Commit đồng thời thay đổi chính sách version và lockfile.

Ví dụ:

```bash
./gradlew :app:test :app:run --write-locks
```

Khi cần cập nhật chọn lọc một nhóm dependency theo policy đã đổi, Gradle còn có `--update-locks`:

```bash
./gradlew :app:test --update-locks org.apache.commons:commons-lang3
```

Lệnh này không tự thay mọi constraint bằng phiên bản mới nhất; nó cập nhật lock cho module được chỉ định trong phạm vi resolution đang chạy. Nếu platform vẫn áp đặt chính sách không cho version mới, `--update-locks` không bỏ qua chính sách đó.

### 5.4. Lockfile không lưu artifact checksum

Lock state chủ yếu giữ **module versions** và mối liên quan tới configuration, không tự đảm bảo JAR có nội dung byte giống nhau nếu repository bị thay artifact. Khi muốn kiểm tra checksum/chữ ký và tính toàn vẹn, sử dụng **dependency verification** kết hợp chính sách repository.

Lockfile cũng không tự khóa tất cả plugin versions như một cơ chế plugin management đầy đủ. Plugin aliases, `pluginManagement` và plugin repositories là các phần khác phải được quản lý đúng.

## 6. Convention plugin: đóng gói cấu hình build dùng chung

Convention plugin là plugin do nhóm xây để nhiều project cùng áp dụng một bộ quy ước, ví dụ:

- Áp dụng `java` hoặc `java-library` theo vai trò.
- Đặt toolchain Java 17.
- Đặt encoding UTF-8 cho các task `JavaCompile`.
- Cấu hình `Test` dùng JUnit Platform.
- Thiết lập compiler warnings/test logging/quality plugins nếu cần.
- Có thể khai báo dependencies, platform hoặc bật locking khi team quyết định.

Phần cuối cùng rất quan trọng: convention plugin **có thể** cấu hình platform/locking, nhưng không **tự** làm việc đó chỉ vì được gọi là convention plugin.

### 6.1. Tại sao nên dùng plugin thay vì copy cùng code?

Nếu 30 project đều có:

```kotlin
java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

tasks.withType<org.gradle.api.tasks.compile.JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
```

việc sửa từ Java 17 sang phiên bản mới có thể phải thay nhiều script. Đưa logic chung vào convention plugin giúp một nơi sở hữu quy ước, giảm copy/paste và dễ kiểm thử.

### 6.2. Các kiểu build logic

| Giải pháp | Phù hợp khi |
| --- | --- |
| Precompiled script plugin trong included build `build-logic` | Muốn quy ước DSL có cấu trúc, tái sử dụng cho nhiều project |
| Binary plugin viết Java/Kotlin/Groovy | Logic phức tạp hoặc cần kiểm thử đơn vị rõ ràng |
| `buildSrc` | Build nhỏ muốn đặt logic chung trực tiếp, chấp nhận đặc điểm lifecycle của `buildSrc` |
| `subprojects { ... }` trong root | Cấu hình đơn giản; càng lớn càng dễ coupling giữa các project |

Trong dự án thực hành, ta dùng **precompiled Kotlin DSL script plugin** trong included build tên `build-logic`. Đây là giải pháp phổ biến cho multi-project và không yêu cầu publish plugin công khai.

## 7. Project mẫu đầy đủ: cả bốn cơ chế và Java 17

Ví dụ sau cho thấy bốn thành phần **hoạt động đồng thời**. Nó gồm hai project chính `:platform`, `:app` và một included build `build-logic`:

```text
dependency-policy-demo/
├── settings.gradle.kts
├── gradle/
│   └── libs.versions.toml
├── platform/
│   └── build.gradle.kts
├── app/
│   ├── build.gradle.kts
│   └── src/
│       ├── main/java/demo/Main.java
│       └── test/java/demo/MainTest.java
└── build-logic/
    ├── build.gradle.kts
    └── src/main/kotlin/java17-conventions.gradle.kts
```

Dùng một phiên bản Gradle hiện đại tương thích JDK 17 và có JDK 17 sẵn hoặc cơ chế cung cấp toolchain phù hợp. Lần đầu resolve thư viện cần Internet và Maven Central (hoặc cache/proxy đã chứa artifact). Không cần Android SDK.

### 7.1. Settings

**File `settings.gradle.kts`:**

```kotlin
pluginManagement {
    includeBuild("build-logic")
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

rootProject.name = "dependency-policy-demo"
include("platform", "app")
```

`pluginManagement.includeBuild` cho phép build chính tìm plugin được cung cấp từ `build-logic`. `dependencyResolutionManagement.repositories` cung cấp Maven Central cho dependencies của app. `include("platform", "app")` tạo hai project của main build; `build-logic` không phải project `:build-logic` của main build mà là **included build riêng**.

### 7.2. Catalog

**File `gradle/libs.versions.toml`:**

```toml
[versions]
junit = "5.10.2"
junit-platform = "1.10.2"

[libraries]
commons-lang3 = { module = "org.apache.commons:commons-lang3" }
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }
junit-platform-launcher = { module = "org.junit.platform:junit-platform-launcher", version.ref = "junit-platform" }
```

Alias `commons-lang3` **không** đặt version: platform sẽ cung cấp constraint cho module này. Hai thư viện phục vụ JUnit 5 có version requests trong catalog. Không có plugin alias ngoài nào cần được tải.

### 7.3. Platform

**File `platform/build.gradle.kts`:**

```kotlin
plugins {
    id("java-platform")
}

dependencies {
    constraints {
        api("org.apache.commons:commons-lang3:3.14.0")
    }
}
```

`java-platform` chỉ định project là nơi chứa dependency constraints. Không cần `src/main/java` hoặc một class Java trong project `:platform`. Constraint `3.14.0` không có nghĩa tất cả consumer tự có commons-lang3; app phải import platform và request module.

### 7.4. Included build tạo convention plugin

**File `build-logic/build.gradle.kts`:**

```kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
}
```

Trong đoạn này, token `kotlin-dsl` cần được bao bởi backticks theo đúng Kotlin DSL; code fence sau khi hiển thị đã có cú pháp `plugins { `kotlin-dsl` }` với dấu backtick. Đây là cú pháp plugin `kotlin-dsl` tích hợp dùng để biên dịch precompiled script plugin.

**File `build-logic/src/main/kotlin/java17-conventions.gradle.kts`:**

```kotlin
plugins {
    java
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

tasks.withType<org.gradle.api.tasks.compile.JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}

tasks.withType<org.gradle.api.tasks.testing.Test>().configureEach {
    useJUnitPlatform()
}
```

Tên file `java17-conventions.gradle.kts` tạo ID plugin `java17-conventions`. Plugin áp dụng `java`, đặt Java 17, encoding và cấu hình `Test`. Nó **không** tự thêm JUnit Jupiter vào test dependencies và **không** tự tạo lockfile.

Trong build có JDK đủ dùng, Gradle biên dịch precompiled script plugin để áp dụng vào app. Nếu cần dùng plugin bên ngoài trong build-logic, phải cấu hình repository và dependencies cho included build; root catalog không mặc nhiên có sẵn trong đó.

### 7.5. App: nối cả bốn thành phần

**File `app/build.gradle.kts`:**

```kotlin
plugins {
    application
    id("java17-conventions")
}

application {
    mainClass.set("demo.Main")
}

dependencies {
    implementation(platform(project(":platform")))
    implementation(libs.commons.lang3)

    testImplementation(libs.junit.jupiter)
    testRuntimeOnly(libs.junit.platform.launcher)
}

dependencyLocking {
    lockAllConfigurations()
}
```

Phân tích từng nhóm:

1. **Convention plugin:** `id("java17-conventions")` áp dụng chính sách Java 17, UTF-8, JUnit Platform.
2. **Platform:** `platform(project(":platform"))` đưa version constraint của commons-lang3 vào graph.
3. **Catalog:** `libs.commons.lang3`, `libs.junit.jupiter`, `libs.junit.platform.launcher` tạo các dependency requests tương ứng.
4. **Locking:** `lockAllConfigurations()` bật chính sách khóa version resolved cho các configurations được quản lý khi chúng được resolve.

`application` cung cấp task `run` và áp dụng các khả năng Java phù hợp; convention plugin cùng áp dụng `java` không tạo hai ứng dụng khác nhau.

### 7.6. Chương trình Java 17

**File `app/src/main/java/demo/Main.java`:**

```java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String input = "hello from gradle";
        System.out.println(StringUtils.capitalize(input));
    }
}
```

Hàm `StringUtils.capitalize` viết hoa ký tự đầu, không tự viết hoa mọi từ.

**File `app/src/test/java/demo/MainTest.java`:**

```java
package demo;

import org.apache.commons.lang3.StringUtils;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

final class MainTest {
    @Test
    void capitalizesFirstCharacter() {
        assertEquals("Hello", StringUtils.capitalize("hello"));
    }
}
```

Đây là test JUnit Jupiter. Convention plugin chọn JUnit Platform; dependency `junit-jupiter` cung cấp API/engine JUnit phù hợp, và `junit-platform-launcher` được khai báo cho runtime của test.

### 7.7. Lệnh build và output

Nếu repo đã có Gradle Wrapper, dùng Wrapper đó. Với thư mục hoàn toàn mới chưa có Wrapper, máy cần một bản Gradle tương thích cài sẵn để chạy một lần:

```bash
gradle wrapper
```

Trên Linux/macOS:

```bash
./gradlew :app:run --quiet
./gradlew :app:test --console=plain
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat :app:run --quiet
.\gradlew.bat :app:test --console=plain
```

Khi dependencies và toolchain được cung cấp chính xác, stdout **do chương trình Main in** là:

```text
Hello from gradle
```

Đây không phải cam kết toàn bộ Gradle log chỉ có một dòng; khi chạy lần đầu có thể có thông báo tải/cấu hình môi trường. Kiểm tra kết quả JUnit bằng trạng thái `:app:test` và báo cáo:

```text
app/build/reports/tests/test/index.html
```

Các kết quả test XML thường nằm dưới `app/build/test-results/test`. Khi test báo `NO-SOURCE` hoặc `SKIPPED`, không nên kết luận kiểm thử đã được thực thi thành công.

### 7.8. Ghi dependency lockfile

Với `dependencyLocking` đã bật, chạy:

```bash
./gradlew :app:test :app:run --write-locks
```

Sau resolution, Gradle thường tạo/cập nhật:

```text
app/gradle.lockfile
```

Lock state có thể bao gồm dependencies bắc cầu và nhiều configurations đã được resolve. Không tự viết lockfile bằng tay dựa trên hai dòng dependencies ở app.

Chạy lại bình thường:

```bash
./gradlew :app:test :app:run
```

Khi dùng CI và Git, nên commit lockfile cùng catalog/platform/build scripts để kiểm soát version đã chọn. Với project khác, file lock của project đó cần được quản lý tương ứng; không suy luận một lockfile của app tự khóa graph của mọi project.

## 8. Kiểm chứng vai trò từng công cụ bằng thí nghiệm

### 8.1. Đổi alias trong catalog

Trong TOML, đổi alias `commons-lang3` thành `text-utils`, giữ nguyên `module` và không thêm version. Trong app, đổi:

```kotlin
implementation(libs.commons.lang3)
```

thành:

```kotlin
implementation(libs.text.utils)
```

Nếu module vẫn là commons-lang3 và platform giữ nguyên, resolved dependency không cần đổi. Tên alias là **giao diện cho build scripts**, không phải identity của Maven artifact.

### 8.2. Bỏ platform nhưng giữ alias không version

Trong bản sao, bỏ:

```kotlin
implementation(platform(project(":platform")))
```

và vẫn giữ `implementation(libs.commons.lang3)`. Lúc này module không được catalog khai báo version và cũng không còn constraint từ platform. Nếu không có nguồn version khác trong graph, Gradle không đủ thông tin để chọn module version và resolution có thể fail.

Thực nghiệm cho thấy catalog chỉ đặt tên, còn platform có thể là **nguồn chính của version policy**. Khôi phục platform sau thử nghiệm.

### 8.3. Cho catalog request một version khác platform

Đổi alias TOML sang:

```toml
[libraries]
commons-lang3 = { module = "org.apache.commons:commons-lang3", version = "3.12.0" }
```

giữ constraint platform ở `3.14.0`. Nếu không bị lock cũ chi phối và không có constraints khác, Gradle thường chọn `3.14.0` theo version conflict resolution. Kiểm tra thay vì đoán:

```bash
./gradlew :app:dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
```

Kết quả minh họa này chứng minh **version trong catalog là request**, không bảo đảm chính nó là version được chọn cuối cùng. Khi lockfile đã được tạo, cần xử lý lock theo quy trình cập nhật thay vì dùng thí nghiệm này để kết luận thiếu chính xác.

### 8.4. Thay platform constraint trong khi có lockfile

Giả sử tổ chức xác nhận một version commons-lang3 mới phù hợp và thay constraint `3.14.0` trong `:platform`. Không nên kỳ vọng lockfile tự thay theo khi chạy build bình thường. Một workflow hợp lệ là:

```bash
./gradlew :app:test :app:run --write-locks
```

Sau đó đọc diff lockfile, chạy lại không có `--write-locks` và review kết quả. Nếu cần cập nhật chọn lọc một module, cân nhắc `--update-locks`. Từ đó thấy sự khác nhau: **platform là policy; locking là resolved state**.

### 8.5. Bỏ convention plugin

Tạm bỏ `id("java17-conventions")` trong app nhưng giữ `application`. Task Java vẫn tồn tại vì application plugin, nhưng toolchain 17, encoding UTF-8 và `useJUnitPlatform()` **do convention plugin cung cấp** không còn tự được cấu hình theo quy ước bài thực hành.

Kết quả tùy JDK đang dùng và cấu hình Gradle còn lại. Không nên giả định chỉ có dependency JUnit Jupiter thì mọi task `test` tự biết chạy JUnit Platform. Khôi phục plugin trước khi chạy lại test chính thức.

### 8.6. Lock chưa được ghi và lock đã ghi

`lockAllConfigurations()` chưa phải một danh sách version cụ thể. Sau khi chạy `--write-locks` và có lockfile được review, build mới có cơ sở lock state. Locking không thay thế việc lựa chọn dependency đúng ban đầu; nó giúp duy trì kết quả đã chọn.

## 9. DependencyInsight, outgoing variants và kiểm tra graph

Một số lệnh hữu ích trong ví dụ:

```bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
./gradlew :app:dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
./gradlew :platform:outgoingVariants
./gradlew javaToolchains
```

Ý nghĩa:

- `dependencies`: đọc graph đã resolve ở **đúng configuration**.
- `dependencyInsight`: xem vì sao một version được chọn, request đến từ đâu, có platform/constraint liên quan không.
- `outgoingVariants`: quan sát những variant mà platform project công bố theo plugin/model.
- `javaToolchains`: xem các toolchains Gradle tìm thấy, hữu ích khi Java 17 không sẵn.

Đừng gán lỗi dependency version cho Java toolchain hoặc ngược lại. Hai lỗi có thể xuất hiện trong cùng build nhưng cần kiểm tra riêng.

## 10. Platform, locking và security/compliance

Platform và locking hữu ích cho tính nhất quán phiên bản, nhưng chúng chưa tạo đủ chuỗi tin cậy:

- **Repository policy:** module đến từ nguồn được phép hay không?
- **Dependency verification:** checksum/chữ ký của artifact có phù hợp không?
- **License/security review:** thư viện có được phép dùng và đã được rà soát rủi ro không?
- **Dependency locking:** resolved version có ổn định giữa các lần build không?
- **Platform constraints:** các modules có tuân thủ version policy chung không?

Nếu một artifact bị publish lại cùng `group:artifact:version` nhưng nội dung đổi, việc khóa version **không tự xác minh byte content**. Nếu CI thiếu repository/credential, lockfile đúng cũng không giúp tải artifact. Khi dùng internal Maven repository, cần giữ quyền truy cập tối thiểu và không để token trong build scripts.

Những bản phát hành thường xuyên nên có quy trình cập nhật dependency, test, kiểm tra CVE/license và review lockfile. Lock không nên bị bỏ qua khi có lỗi nhưng cũng không nên bị giữ mãi không update.

## 11. Lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `Unresolved reference: libs` | Catalog chưa nạp, sai build scope, included build không có catalog | Kiểm tra `gradle/libs.versions.toml` và settings |
| Alias không được IDE nhận diện | Tên alias sai hoặc model chưa được đồng bộ | Đọc TOML, reload Gradle model |
| Đã khai báo library trong TOML nhưng app thiếu class | Chưa dùng alias trong dependencies | Thêm vào `implementation`/configuration đúng |
| Version resolved khác catalog | Constraints/graph/lock chi phối | Chạy `dependencyInsight` |
| Import platform nhưng không có thư viện trên classpath | Platform không tự thêm dependency | Khai báo module trực tiếp/bắc cầu phù hợp |
| `java-platform` không có `constraints.api` | Thiếu plugin hoặc sai cấu hình | Dùng `plugins { id("java-platform") }` |
| Enforced platform làm lỗi consumer | Version bị áp đặt quá mạnh | Xem lại regular platform và constraints |
| Nâng platform nhưng build fail vì lock | Lock state chưa cập nhật cho graph mới | Review và dùng `--write-locks` |
| Lockfile thiếu dependency mong đợi | Configuration tương ứng chưa resolve/ghi lock | Chạy task resolution đúng configuration |
| Build offline fail dù đã lock | Artifact/metadata chưa có cache | Kiểm tra repository/cache/`--offline` |
| `java17-conventions` not found | Chưa `includeBuild("build-logic")` hoặc sai plugin ID/tên file | Kiểm tra settings/file path |
| `build-logic` không thấy `libs` | Included build độc lập, catalog không tự chia sẻ | Chủ động cấu hình catalog cho included build nếu cần |
| JUnit 5 test không chạy | Thiếu dependencies hoặc `useJUnitPlatform()` | Kiểm tra plugin và task `Test` |
| Java compile dùng version khác 17 | Convention plugin không áp dụng hoặc toolchain không có | Xem `javaToolchains` và `compileJava --info` |
| CI dùng artifact khác laptop dù cùng versions | Nguồn repository, checksum, JDK hoặc môi trường khác | Quản lý verification, Wrapper, toolchain, CI |
| Build có `UP-TO-DATE` nhưng không được cache output | Up-to-date và build cache là hai cơ chế khác | Phân biệt `UP-TO-DATE` với `FROM-CACHE` |

### Quy trình debug ngắn

1. **Tìm module thật**: alias TOML ánh xạ tới `group:artifact` nào?
2. **Xem nơi đặt version**: catalog, platform, constraint, dependency trực tiếp hay transitive?
3. **Xem configuration**: `compileClasspath` hay `runtimeClasspath`? Có import platform không?
4. **Xem lock state**: lockfile đã được tạo/commit/cập nhật chưa?
5. **Chạy dependencyInsight** và đọc selected version.
6. **Nếu lỗi Java/toolchain**, kiểm tra convention plugin và JDK thay vì thay dependencies vô cớ.
7. **Nếu lỗi tải artifact**, kiểm tra Maven repositories, network, credentials và verification.
8. **Chạy test thực**, không chỉ xem dependency graph.

## 12. Thiết kế trách nhiệm trong một tổ chức

Một cách phân chia dễ bảo trì:

| Vùng sở hữu | Nội dung nên quản lý |
| --- | --- |
| `gradle/libs.versions.toml` | Tên aliases, module coordinates, version requests phù hợp |
| `:platform` | Constraints cho những thư viện cần alignment |
| `app/gradle.lockfile` | Versions đã resolve của app theo cấu hình locking |
| `build-logic` | Java toolchain, test framework config, các convention tasks/plugins |
| `settings.gradle.kts` | Project includes, plugin build, repository policy |
| `gradle/wrapper` | Gradle distribution cho nhóm/CI |
| Dependency verification metadata | Artifact integrity nếu dự án dùng verification |

Không nhất thiết có đầy đủ mọi vùng trong project nhỏ. Nhưng khi build có nhiều module, tách trách nhiệm giúp bạn trả lời “version này đến từ đâu?” và “đoạn cấu hình JUnit này đến từ đâu?” mà không phải đọc mọi build script.

**Mẹo:** nếu một convention plugin muốn tự thêm platform dependency, hãy đặt điều đó thật rõ trong plugin hoặc tạo plugin chuyên cho policy dependency. Đừng ngầm buộc mọi module, kể cả platform project hoặc module không có Java, phải chịu cấu hình không phù hợp.

## 13. Bài tập vận dụng

**Bài tập A — nối công cụ với chức năng.** Từ bốn nhu cầu: đặt tên library, đồng bộ constraints, giữ resolved version, cấu hình Java 17/JUnit, hãy chọn công cụ phù hợp và giải thích vì sao không thay thế cho nhau.

**Bài tập B — chạy project mẫu.** Tạo các file ở mục 7, chạy `:app:run`, `:app:test` và kiểm tra stdout `Hello from gradle` cùng báo cáo test. Toolchain 17 đến từ đâu? Version commons-lang3 đến từ đâu?

**Bài tập C — đổi alias.** Đổi `commons-lang3` thành `text-utils` trong catalog, sửa accessor ở app, rồi chạy dependencyInsight. Vì sao module thật không đổi?

**Bài tập D — bỏ platform.** Giữ alias commons-lang3 không version nhưng bỏ import platform ở app. Dự đoán resolution và lý do. Khôi phục sau khi thử.

**Bài tập E — platform và catalog xung đột.** Thêm version request `3.12.0` cho catalog alias trong bản sao, giữ constraint platform `3.14.0`. Đọc dependencyInsight. Khi đã có lockfile, cần làm gì trước khi kết luận bản nào được chọn?

**Bài tập F — tạo lockfile.** Chạy `:app:test :app:run --write-locks`, mở `app/gradle.lockfile`, xem các module versions và configurations. Chạy lại bình thường. Tại sao nên commit file này trong CI workflow?

**Bài tập G — nâng version policy.** Đổi platform constraint thành version đã được nhóm xác nhận tương thích. Cập nhật lock theo quy trình và xem diff. Vì sao lockfile không tự “theo” mọi thay đổi của platform mà không cần quyết định cập nhật?

**Bài tập H — thử gỡ convention plugin.** Trong bản sao app, gỡ plugin `java17-conventions`, quan sát sự khác nhau ở Java toolchain và task `test`. Thử chạy test rồi khôi phục plugin. Đâu là phần trách nhiệm của convention plugin, đâu là phần của JUnit dependency?

**Bài tập I — so sánh cache.** Sau khi có lockfile, chạy `--offline` trên máy đã có cache và trên môi trường sạch. Giải thích vì sao cùng lockfile không đảm bảo offline build thành công.

**Bài tập J — mô hình cho nhiều ứng dụng.** Thiết kế build gồm `:platform` dùng chung, catalog aliases, convention plugins theo loại module và lockfiles của từng app. Nêu cách nhóm review thay đổi platform và lockfiles mà không tạo sự lệ thuộc ngầm.

### Câu hỏi tự kiểm tra

1. Version catalog có tự đưa thư viện vào classpath không?
2. Version nằm trong TOML có chắc là resolved version cuối không?
3. Platform constraint có tự tải mọi dependency mà nó nhắc tới không?
4. `platform(...)` và `enforcedPlatform(...)` khác nhau ra sao?
5. `strictly(...)` có khác regular version constraint không?
6. `lockAllConfigurations()` có tự tạo lockfile nếu chưa resolve configuration nào không?
7. Muốn ghi lock state, lệnh gì thường được dùng?
8. Vì sao phải review lockfile mỗi lần nâng dependency?
9. Lockfile có xác minh checksum artifact không?
10. Convention plugin có tự quản lý mọi version không?
11. Tại sao `build-logic` không tự thấy catalog `libs` của main build?
12. Precompiled plugin ID `java17-conventions` đến từ file nào?
13. `useJUnitPlatform()` và `testImplementation(libs.junit.jupiter)` giải quyết hai việc khác nhau thế nào?
14. Có thể dùng catalog mà không có platform không?
15. Có thể dùng platform mà không có catalog không?
16. Vì sao CI cần cả Wrapper, toolchain, repository và lock state thay vì chỉ catalog?
17. Khi `dependencyInsight` hiện version khác TOML, cần kiểm tra những nguồn version nào?
18. `--offline` và `--write-locks` tác động hai phần khác nhau thế nào?
19. Khi nào convention plugin phù hợp hơn chép block `subprojects`?
20. Thử nghiệm nào chứng minh platform và convention plugin có vai trò khác nhau?

**Ghi nhớ:** **Version catalog** làm rõ tên và tạo dependency requests; **platform** cung cấp constraints để chọn phiên bản tương thích; **dependency locking** giữ version resolved của graph; **convention plugin** tái sử dụng logic cấu hình Gradle. Kết hợp chúng theo trách nhiệm rõ ràng, kiểm chứng bằng `dependencyInsight`, lockfile, Java compilation và test thực tế để có build vừa dễ bảo trì vừa đáng tin cậy.
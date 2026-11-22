# Included build `build-logic` và cơ chế phát triển plugin nội bộ trong Gradle

## 1. Mục tiêu và ngữ cảnh

Bài thuộc nhóm **Build logic dùng chung** của chủ đề **Build Tool Gradle**. Khi một repository có nhiều Java modules, việc sao chép `java.toolchain`, encoding UTF-8, JUnit, Checkstyle, JaCoCo và chính sách publish vào mỗi file `build.gradle.kts` sẽ nhanh chóng dẫn đến sai lệch giữa các module. Đặt tất cả vào root `subprojects { ... }` cũng không phải giải pháp tối ưu: module khó tự quyết định policy, cấu hình giữa các projects bị ràng buộc chéo và việc kiểm thử build logic khó tách biệt.

**Convention plugin** là một plugin có tên, gói các quy ước build dùng chung và được mỗi module áp dụng rõ ràng bằng `plugins { id("...") }`. Một cách phát triển plugin nội bộ phổ biến là đặt mã plugin trong **included build** tên `build-logic`, được root Settings khai báo qua `pluginManagement { includeBuild("build-logic") }`. Gradle sẽ xây dựng plugin từ source trong composite build rồi dùng nó khi cấu hình modules; không cần publish lên Maven chỉ để dùng trong cùng repository.

Bài học cung cấp hai con đường:

1. **Precompiled Kotlin DSL script plugin:** tiện nhất cho quy ước Java/Tests, ví dụ hoàn chỉnh Java 17 + JUnit Jupiter và stdout chính xác.
2. **Binary plugin bằng Java:** phù hợp task type, extension/API phức tạp, có ví dụ `Plugin<Project>`, `@TaskAction` và functional test bằng Gradle TestKit.

Sau bài, bạn cần hiểu khác biệt giữa **subproject**, **included build**, **buildSrc**, **plugin repositories** và **application dependencies**; có thể xây dựng/test/reuse plugin nội bộ, cấu hình task lazy, dùng Configuration Cache và chẩn đoán lỗi plugin resolution.

## 2. Build logic dùng chung: các lựa chọn

| Cách triển khai | Phù hợp | Rủi ro/giới hạn |
| --- | --- | --- |
| Copy cấu hình vào từng module | Một project nhỏ, ít lặp | Version/policy drift |
| `apply(from = "shared.gradle.kts")` | Script legacy/thử nghiệm | Không được khuyến khích với hệ thống lớn, thiếu một số Kotlin DSL accessors |
| `buildSrc` | Logic nội bộ một repo cần thiết lập nhanh | Gradle tự thêm classpath cho toàn build, sửa có thể khiến nhiều project phải cấu hình lại |
| **Included build `build-logic`** | Convention plugins được tổ chức/test độc lập | Cần `includeBuild`, Settings và repositories riêng |
| Published binary plugin | Dùng qua nhiều repositories/đội, cần version/release riêng | Phải quản lý marker, publishing, compatibility/security |

`build-logic` là **tên thư mục thông thường theo convention**, Gradle không tự nhận diện. `buildSrc` mới là thư mục đặc biệt được Gradle tự tìm và compile trước khi cấu hình main build.

### 2.1. Conceptual comparison

~~~text
Multi-project root build:
  include(":library")
  include(":app")
    -> subprojects chung một Settings/build tree

Composite build:
  pluginManagement { includeBuild("build-logic") }
    -> build-logic là Gradle build riêng,
       có settings.gradle.kts và build.gradle.kts riêng

buildSrc:
  thư mục tên buildSrc tự động được Gradle phát hiện
    -> không cần includeBuild trong settings
~~~

### 2.2. Không nhầm include với includeBuild

~~~kotlin
include(":build-logic")
~~~

tạo một **subproject**, không có nghĩa cung cấp một plugin build thông qua plugin resolution.

~~~kotlin
pluginManagement {
    includeBuild("build-logic")
}
~~~

chỉ định một **included plugin build** cho `plugins {}` trong project build scripts. Với plugin nội bộ, đây là cách rõ ràng, tránh phụ thuộc vào command-line `--include-build` vốn không phải lựa chọn đáng tin cậy nhất cho unpublished plugin IDs trong modern plugin DSL.

## 3. Kiến trúc bài lab hoàn chỉnh

Bài lab dùng root đa module một project `:library` và included build độc lập:

~~~text
build-logic-demo/
├── settings.gradle.kts
├── build-logic/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/main/kotlin/
│       └── acme.java-library-conventions.gradle.kts
├── library/
│   ├── build.gradle.kts
│   └── src/
│       ├── main/java/demo/Greeting.java
│       └── test/java/demo/GreetingTest.java
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
~~~

Yêu cầu: Gradle Wrapper của repo đủ mới cho Kotlin DSL/precompiled script plugin và Java toolchain, JDK 17 có sẵn/provision được, Maven Central hoặc mirror được phép để resolve JUnit. Nếu mới tạo folder trống, cần tạo Wrapper theo chính sách dự án; **không dùng wrapper JAR/checksum không rõ nguồn**.

Root không cần `build.gradle.kts` cho lab này vì không có cấu hình root project đặc biệt. Hệ thống lớn có thể thêm root file để khai báo reporting/aggregation tasks, nhưng không cần dùng `subprojects` để ép policy lên toàn bộ module.

## 4. Root settings.gradle.kts

Tạo `build-logic-demo/settings.gradle.kts`:

~~~kotlin
pluginManagement {
    // Cung cấp plugin từ source nằm trong included build.
    includeBuild("build-logic")

    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = "build-logic-demo"

include(":library")
~~~

Giải thích:

- `pluginManagement` xuất hiện ở đầu Settings script như Gradle yêu cầu.
- `includeBuild("build-logic")` đưa plugin build vào **plugin resolution**.
- `pluginManagement.repositories` dành cho plugin artifacts/markers, không tự cung cấp repositories cho Java/JUnit dependencies.
- `include(":library")` là module Java bình thường, hoàn toàn khác included build.
- Source path tương đối được giải từ root chứa Settings, không phụ thuộc vào đường dẫn tuyệt đối trên máy developer.

**Đừng thay `includeBuild("build-logic")` bằng `include(":build-logic")`** rồi thắc mắc vì sao `plugins { id("acme.java-library-conventions") }` báo not found.

## 5. build-logic/settings.gradle.kts

Tạo file Settings của included build:

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = "build-logic"
~~~

Included build có **Settings độc lập**; cấu hình root `pluginManagement` hoặc `dependencyResolutionManagement` không tự thừa kế vào đây. Nếu build logic cần một private repository để tải external plugin implementation, cấu hình nó trong đúng context hoặc dùng convention/enterprise settings được tổ chức phê duyệt.

Một included build có thể tự được chạy để kiểm tra:

~~~bash
./gradlew -p build-logic tasks --console=plain
~~~

Lệnh dùng Gradle Wrapper tại root, với project directory hướng đến build logic. Included build **không phải** subproject của root dù task names có thể được Gradle tham chiếu qua included-build task paths trong một số hoạt động.

## 6. build-logic/build.gradle.kts

File tối thiểu cho precompiled Kotlin DSL plugin:

~~~kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}
~~~

`kotlin-dsl` là plugin hỗ trợ compile các file `.gradle.kts` trong `src/main/kotlin` thành plugin classes/descriptors có thể được apply bằng ID. Không cần khai báo thủ công `implementationClass` khi viết **precompiled script plugin**, vì Gradle tạo plugin class và ID dựa vào file source.

`repositories` trong build này dùng để resolve **plugin build dependencies**; không tự thêm `mavenCentral` vào `:library`. Nếu `kotlin-dsl` plugin không resolve hoặc thiếu Gradle Plugin Portal trong môi trường CI, kiểm tra plugin management và mirror chính thức, không lấy JAR ngẫu nhiên.

## 7. Tạo convention plugin Java 17

Tạo file:

`build-logic/src/main/kotlin/acme.java-library-conventions.gradle.kts`

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.Test
import org.gradle.jvm.toolchain.JavaLanguageVersion

plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    // Java source/UTF-8, kể cả các literal tiếng Việt.
    options.encoding = "UTF-8"

    // Java API và class-file target Java 17.
    options.release.set(17)
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()

    testLogging {
        events("passed", "skipped", "failed")
    }
}
~~~

Đây là một **precompiled project script plugin độc lập và đầy đủ**. File có hậu tố `.gradle.kts`, không phải Java/Kotlin source class. Gradle suy ra plugin ID:

~~~text
Source filename:
acme.java-library-conventions.gradle.kts

Plugin ID:
acme.java-library-conventions
~~~

Plugin ID không nên trùng core plugin hoặc bắt đầu bằng `org.gradle`. Chọn namespace của nhóm để giảm xung đột với plugin ngoài.

### 7.1. Chính sách do plugin áp dụng

- Áp `java-library` cho project consumer.
- Cấu hình `java.toolchain` Java 17.
- Chọn compiler `options.encoding="UTF-8"`.
- Đặt `options.release.set(17)` để ràng buộc Java API/bytecode target.
- Cho các task `Test` dùng JUnit Platform.
- Cấu hình test events trên console.

**Chưa có JUnit dependency** ở đây: `useJUnitPlatform()` không tự thêm JUnit Jupiter API/engine/launcher. Module phải khai báo JUnit hoặc một convention plugin riêng phải quản lý test dependencies.

### 7.2. Cách accessors được tạo

Precompiled plugin có:

~~~kotlin
plugins {
    `java-library`
}
~~~

Gradle có thể tạo Kotlin DSL type-safe model accessors cho Java extension/tasks/configurations do plugin khai báo sớm trong `plugins` block. Nếu thay bằng:

~~~kotlin
apply(plugin = "java-library")
~~~

trong phần thân script thì mô hình accessors được tạo tĩnh không giống khi plugin nằm ở `plugins` block. Khi chưa có accessor, dùng API typed như `extensions.getByType<JavaPluginExtension>()`/`tasks.named(...)`/`tasks.withType(...)`, không giả định extension sẽ hiện tự động.

Trong **binary plugin Java**, không có Kotlin DSL extension accessor; dùng trực tiếp Java Gradle API.

### 7.3. Cấu hình lazy

`tasks.withType<JavaCompile>().configureEach` áp cho tasks hiện có và tasks được đăng ký về sau mà không buộc realize tất cả tasks ngay lúc cấu hình. Tương tự `tasks.named`, `tasks.register` tốt hơn cách tạo/eager configuration vô tội vạ. Mục đích là một policy nhỏ, dễ test và tương thích với Gradle configuration avoidance.

## 8. Consumer module áp dụng plugin

Tạo `library/build.gradle.kts`:

~~~kotlin
plugins {
    id("acme.java-library-conventions")
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.10.2"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
~~~

Library **không phải apply lại `java-library`**, vì convention plugin đã làm. Nó cũng không phải copy toolchain/encoding/release và `useJUnitPlatform()`.

JUnit 5 BOM `5.10.2` là phiên bản cố định minh họa, không tuyên bố mới nhất. Team thật nên quản lý versions/mirrors theo policy. Maven Central ở đây để resolve JUnit trong module, không phải nơi publish internal plugin.

### 8.1. Vì sao không ghi version khi áp internal plugin?

~~~kotlin
plugins {
    id("acme.java-library-conventions")
}
~~~

Plugin lấy từ **source included build** đã được Settings đăng ký; không cần `version "1.0.0"` trong module. Khi plugin được publish dạng binary qua một repository dùng nhiều project/repository, consumers mới cần version/resolution policy phù hợp.

### 8.2. Không dùng implementation(project(":build-logic"))

~~~kotlin
dependencies {
    implementation(project(":build-logic"))
}
~~~

không có ý nghĩa cho example: `build-logic` là **included build/plugin provider**, không phải Java application library subproject. Thêm plugin JAR vào application `implementation` cũng không thay việc plugin phải được áp trong `plugins {}` tại configuration phase.

## 9. Java 17 example có stdout đúng

### 9.1. library/src/main/java/demo/Greeting.java

~~~java
package demo;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String name) {
        return "Xin chào, " + name + "!";
    }

    public static void main(String[] args) {
        System.out.println(message("Lan"));
    }
}
~~~

Lớp Java này không phụ thuộc external libraries; `message("Lan")` trả string chính xác và `main` in một dòng.

### 9.2. library/src/test/java/demo/GreetingTest.java

~~~java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingTest {
    @Test
    void hasVietnameseGreeting() {
        assertEquals(
            "Xin chào, Lan!",
            Greeting.message("Lan")
        );
    }
}
~~~

Có một test method `@Test` sử dụng JUnit Jupiter. Gradle Java Library plugin chuẩn bị classes/resources test; convention plugin cấu hình JUnit Platform; `library/build.gradle.kts` cung cấp JUnit API/engine/launcher.

## 10. Các lệnh chạy đầy đủ

Tại root `build-logic-demo/`.

**Linux/macOS:**

~~~bash
./gradlew :library:clean :library:test --console=plain
./gradlew :library:classes --console=plain
java -cp library/build/classes/java/main demo.Greeting
~~~

**Windows PowerShell:**

~~~powershell
.\gradlew.bat :library:clean :library:test --console=plain
.\gradlew.bat :library:classes --console=plain
java -cp library\build\classes\java\main demo.Greeting
~~~

**Stdout chính xác do Java main in ra:**

~~~text
Xin chào, Lan!
~~~

JUnit test kỳ vọng pass với một test method. Gradle logs không có chuỗi cố định do version/cache/OS khác nhau, nên không bịa transcript `BUILD SUCCESSFUL` cụ thể. Kiểm tra task outcome, test report và Java stdout.

### 10.1. Chạy javac/java thuần để kiểm chứng Java source

Vì production code chỉ dùng JDK 17, cũng có thể compile độc lập:

~~~bash
mkdir -p out
javac -encoding UTF-8 --release 17 \
  -d out library/src/main/java/demo/Greeting.java
java -cp out demo.Greeting
~~~

**Stdout:**

~~~text
Xin chào, Lan!
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -encoding UTF-8 --release 17 -d out library\src\main\java\demo\Greeting.java
java -cp out demo.Greeting
~~~

Đây là phép kiểm tra Java source, **không xác minh plugin Gradle đã áp**. Phép kiểm tra plugin phải dùng Gradle CLI.

### 10.2. Xem task graph và compiler logs

~~~bash
./gradlew :library:test --dry-run --console=plain
./gradlew :library:compileJava --info --console=plain
./gradlew :library:tasks --all --console=plain
~~~

`--dry-run` không chạy task actions và không thực thi assertions, chỉ hiển thị graph. `--info` giúp xem toolchain/compiler và lý do task chạy hoặc up-to-date; đừng giả định một log line duy nhất xuất hiện trong mọi Gradle version.

## 11. Cơ chế apply internal plugin theo thứ tự

~~~text
Root settings.gradle.kts
   pluginManagement.includeBuild("build-logic")
                   |
                   v
Included build: build-logic
   kotlin-dsl
   precompiled script source
                   |
                   v
Compiled plugin class + descriptor/classpath
                   |
                   v
:library/build.gradle.kts
   plugins { id("acme.java-library-conventions") }
                   |
                   v
java-library + Java17/UTF-8 + Test policies
                   |
                   v
:library:compileJava, :library:test, :library:jar
~~~

Các bước:

1. Gradle đọc Settings, nhận diện plugin-providing included build.
2. Khi project script yêu cầu ID, Gradle build/resolve implementation classpath của plugin từ `build-logic`.
3. Plugin được apply trong giai đoạn **configuration**, tạo Java source sets và cấu hình tasks.
4. Gradle hoàn tất task graph rồi thực thi tasks trong **execution phase**.
5. Kết quả task có thể được tái sử dụng qua up-to-date/build cache/configuration cache theo inputs.

**Không hiểu sai:** Plugin classpath của build logic **không tự thành** `runtimeClasspath` của ứng dụng Java. Nếu plugin dùng dependency ngoài để chạy Gradle API, dependency đó thuộc môi trường build plugin; Java app chỉ có những dependencies khai báo cho module.

## 12. Included build khác composite dependency substitution

Composite build còn hỗ trợ **dependency substitution** để Gradle thay module dependency trong repository bằng một project thuộc included build phù hợp. Ví dụ khi cùng phát triển một Java library và ứng dụng tiêu thụ library đó, có thể dùng `includeBuild("some-library")` để không phải publish bản thử.

Đó là use case khác với bài này:

- **Plugin build:** cung cấp ID qua `pluginManagement.includeBuild` và chạy trên build-script classpath.
- **Library included build:** có thể thay `implementation("org:module:version")` bằng một project local, phục vụ build/test application.

Đừng vô tình dựa vào library dependency substitution để chứng minh internal convention plugin đã được resolve; hai cơ chế dùng classpath và mục tiêu khác nhau.

## 13. Khi nào nên dùng buildSrc thay cho build-logic?

`buildSrc` được Gradle nhận diện tự động và build trước main build scripts. Nó phù hợp một codebase nhỏ hoặc một giai đoạn chuyển đổi. Mặt trái là classpath rộng hơn và thay đổi `buildSrc` có thể làm nhiều project configurations invalid.

`build-logic` explicit included build:

- Có Settings và repositories riêng.
- Có thể build/test độc lập.
- Là ranh giới ownership rõ.
- Chứa nhiều convention/binary plugins.
- Có thể cho từng module chỉ áp plugin phù hợp.

**Không hứa** included build luôn nhanh hơn: hiệu năng phụ thuộc Gradle version, dependency graph, compilation/cache, file changes và cách plugin được cấu hình. Thay đổi plugin dùng chung vẫn có thể buộc các modules sử dụng nó reconfigure.

### 13.1. Tránh cross-project configuration

Ví dụ phản mẫu:

~~~kotlin
subprojects {
    apply(plugin = "java-library")
    tasks.withType<JavaCompile>().configureEach {
        options.encoding = "UTF-8"
    }
}
~~~

Code này làm module bị cấu hình từ bên ngoài, có thể ảnh hưởng configuration-on-demand/Isolated Projects và khó biết module nào thật sự cần Java Library.

Thay bằng module áp plugin:

~~~kotlin
plugins {
    id("acme.java-library-conventions")
}
~~~

Mỗi module tự tuyên bố policy, làm build script dễ review hơn.

## 14. Phân lớp convention plugins

Khi repository lớn, có thể chia:

~~~text
acme.java-base-conventions
acme.java-library-conventions
acme.java-application-conventions
acme.java-testing-conventions
acme.java-quality-conventions
acme.publish-library-conventions
~~~

Tên này là **ví dụ về cấu trúc**, chưa có sẵn trong bài lab trừ `acme.java-library-conventions`.

- Base: toolchain, encoding, compiler flags.
- Library: Java Library plugin, API/implementation policy.
- Application: Application plugin, mainClass/run/distribution.
- Testing: JUnit/IntegrationTest suites.
- Quality: Checkstyle/PMD/JaCoCo/SpotBugs policy.
- Publishing: MavenPublication, POM/licenses, signing/repository rules.

Một module có thể apply nhiều plugin **không xung đột về ownership**. Ví dụ quality plugin không nên tùy tiện đổi Java toolchain của base plugin; publishing plugin không nên tự áp vào mọi module không publish.

### 14.1. Mỗi policy có một chủ sở hữu

Nếu plugin A set Java 17, plugin B set Java 21, kết quả có thể phụ thuộc configuration order. Cần quy định plugin nào kiểm soát Java version, có được override không và behavior khi hai plugin cùng được áp.

Trong custom extensions, `Property<T>.convention(default)` thường phù hợp để cấp default có thể override; `.set(value)` đặt giá trị cấu hình trực tiếp. Không dựa vào `afterEvaluate` để vá overrides khi Providers và plugin typed APIs có thể xử lý.

## 15. External plugin trong precompiled script plugin

Với core plugin như `java-library`, không cần khai báo version/dependency plugin riêng. Nhưng khi convention plugin áp một plugin ngoài (ví dụ Kotlin JVM hoặc formatting plugin), phải **đưa implementation artifact của plugin ngoài vào dependencies của `build-logic`**.

Một precompiled script plugin viết theo mô hình:

~~~kotlin
plugins {
    id("com.example.external-plugin")
}
~~~

Đây là **cú pháp minh họa**, không phải một external plugin ID đã được xác minh. Để hoạt động, plugin implementation phải thực sự có trên classpath của included plugin build và plugin ID chính xác.

**Không dùng** trong file precompiled script:

~~~kotlin
plugins {
    id("com.example.external-plugin") version "1.2.3"
}
~~~

Gradle docs nêu cú pháp `version "..."` và `apply false` **không hỗ trợ** bên trong precompiled script plugins. Version được quản lý ở dependency của plugin build, không ở script apply. Khi chưa có implementation dependency, có thể gặp plugin not found dù root `pluginManagement.repositories` đã có plugin portal.

### 15.1. Ba context repository độc lập

| Context | Dùng cho |
| --- | --- |
| Root `pluginManagement.repositories` | Tìm plugin IDs/markers trong root build |
| `build-logic` pluginManagement + `repositories` | Plugin development tooling và dependencies để compile plugin |
| Module `library.repositories` | JUnit và Java application dependencies |

Một included build **không tự thừa kế** root repositories/version catalogs. Nếu môi trường bật `repositoriesMode.FAIL_ON_PROJECT_REPOS`, phải khai báo dependency repositories tại nơi được policy cho phép; không sao chép nguyên module repositories từ lab khi bị cấm.

## 16. Version Catalog giữa root và build-logic

Một root có thể có:

~~~text
gradle/libs.versions.toml
~~~

để tập trung JUnit/plugin/library versions. Nhưng `build-logic` có Settings riêng nên **không tự động** nhìn thấy root `libs`.

Nếu cần reuse catalog, thêm vào `build-logic/settings.gradle.kts`:

~~~kotlin
dependencyResolutionManagement {
    versionCatalogs {
        create("libs") {
            from(files("../gradle/libs.versions.toml"))
        }
    }
}
~~~

Đây là **mảnh mở rộng**, chỉ hợp lệ khi file root catalog thực sự có. Không dán vào lab tối giản nếu chưa tạo `gradle/libs.versions.toml`.

Catalog quản lý aliases/version declarations, **không** tự publish plugin và không thay `includeBuild`. Với precompiled script plugins, cẩn trọng khi dùng plugin aliases trong `plugins {}` vì phiên bản/classpath plugin cần được xác định theo cơ chế compile plugin build. Đọc docs theo Gradle Wrapper, ưu tiên khai báo external plugin implementation dependencies trong build-logic.

## 17. Cơ chế binary plugin bằng Java: lựa chọn nâng cao

Precompiled script plugin thích hợp cấu hình theo Gradle DSL. Khi cần custom task có `@Input`/`@OutputFile`, extension `Property<T>`, API Gradle phức tạp, hoặc cần publish sang nhiều repositories, binary plugin implement `Plugin<Project>` thường dễ test/reuse hơn.

**Phương án B bên dưới là ví dụ thay thế**, không trộn nguyên xi với cấu hình precompiled plugin của phần 4–10 trong cùng build-logic. Hãy sử dụng một bản sao repo để thực hành binary plugin.

### 17.1. Binary plugin directory

~~~text
build-logic/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    ├── main/java/dev/acme/buildlogic/
    │   ├── JavaPolicyPlugin.java
    │   └── PrintPolicyTask.java
    └── test/java/dev/acme/buildlogic/
        └── JavaPolicyPluginFunctionalTest.java
~~~

Root Settings vẫn dùng `pluginManagement.includeBuild("build-logic")`, included Settings có plugin repositories riêng.

### 17.2. build-logic/build.gradle.kts cho binary plugin

~~~kotlin
plugins {
    `java-gradle-plugin`
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

gradlePlugin {
    plugins {
        create("javaPolicy") {
            id = "acme.java-policy"
            implementationClass =
                "dev.acme.buildlogic.JavaPolicyPlugin"
        }
    }
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.10.2"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
~~~

`java-gradle-plugin` là Java Gradle Plugin Development plugin. `gradlePlugin` đăng ký ID và implementation class để Gradle tạo plugin descriptors. Nó cũng hỗ trợ Gradle TestKit plugin-under-test classpath. Không cần tự tạo plugin marker metadata bằng tay cho included build.

### 17.3. JavaPolicyPlugin.java

**build-logic/src/main/java/dev/acme/buildlogic/JavaPolicyPlugin.java**

~~~java
package dev.acme.buildlogic;

import org.gradle.api.Plugin;
import org.gradle.api.Project;
import org.gradle.api.plugins.JavaPluginExtension;
import org.gradle.api.tasks.compile.JavaCompile;
import org.gradle.jvm.toolchain.JavaLanguageVersion;

public final class JavaPolicyPlugin implements Plugin<Project> {
    @Override
    public void apply(Project project) {
        project.getPluginManager().apply("java-library");

        JavaPluginExtension java =
                project.getExtensions()
                        .getByType(JavaPluginExtension.class);

        java.getToolchain()
                .getLanguageVersion()
                .set(JavaLanguageVersion.of(17));

        project.getTasks()
                .withType(JavaCompile.class)
                .configureEach(task -> {
                    task.getOptions().setEncoding("UTF-8");
                    task.getOptions().getRelease().set(17);
                });

        project.getTasks().register(
                "printJavaPolicy",
                PrintPolicyTask.class,
                task -> {
                    task.setGroup("help");
                    task.setDescription(
                        "Prints the Java build conventions."
                    );
                }
        );
    }
}
~~~

Đây là Java 17 hợp lệ khi compile trong Gradle plugin project có Gradle API classpath. `Plugin<Project>.apply(Project)` chạy trong configuration phase, còn `PrintPolicyTask` action thực thi ở execution phase. **Không** đặt `System.out.println` trong apply và coi đó là task đã thực thi.

### 17.4. PrintPolicyTask.java

**build-logic/src/main/java/dev/acme/buildlogic/PrintPolicyTask.java**

~~~java
package dev.acme.buildlogic;

import org.gradle.api.DefaultTask;
import org.gradle.api.tasks.TaskAction;

public abstract class PrintPolicyTask extends DefaultTask {
    @TaskAction
    public void printPolicy() {
        getLogger().lifecycle("Policy: Java 17 / UTF-8");
    }
}
~~~

Task type chỉ log một thông điệp cố định, không đọc live `Project`/Gradle model ở execution phase và không được tuyên bố `@CacheableTask` vì không tạo output. Với custom task sinh file thật, cần property annotations, Providers và output declarations thích hợp.

### 17.5. Module áp dụng binary plugin

Trong phương án B, file `library/build.gradle.kts` thay plugins block:

~~~kotlin
plugins {
    id("acme.java-policy")
}
~~~

Vẫn có thể giữ repositories/JUnit dependencies và Java sources từ ví dụ A nếu muốn. Chạy từ root:

~~~bash
./gradlew :library:printJavaPolicy --console=plain
~~~

Thông điệp task chính xác:

~~~text
Policy: Java 17 / UTF-8
~~~

Gradle có thể in thêm task headers/status; không coi một dòng này là toàn bộ stdout.

## 18. Functional testing bằng Gradle TestKit

Gradle TestKit chạy một Gradle build fixture thực tế trong temporary directory. Đây là cách tốt để kiểm tra plugin **được resolve bằng ID và task actions hoạt động**, khác với unit test giả lập `Project`.

### 18.1. JavaPolicyPluginFunctionalTest.java

**build-logic/src/test/java/dev/acme/buildlogic/JavaPolicyPluginFunctionalTest.java**

~~~java
package dev.acme.buildlogic;

import java.nio.file.Files;
import java.nio.file.Path;
import org.gradle.testkit.runner.BuildResult;
import org.gradle.testkit.runner.GradleRunner;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertTrue;

class JavaPolicyPluginFunctionalTest {
    @TempDir
    Path testProjectDir;

    @Test
    void internalPluginCanBeApplied() throws Exception {
        Files.writeString(
            testProjectDir.resolve("settings.gradle.kts"),
            "rootProject.name = \"fixture\"\n"
        );

        Files.writeString(
            testProjectDir.resolve("build.gradle.kts"),
            "plugins { id(\"acme.java-policy\") }\n"
        );

        BuildResult result = GradleRunner.create()
                .withProjectDir(testProjectDir.toFile())
                .withArguments("printJavaPolicy", "--stacktrace")
                .withPluginClasspath()
                .build();

        assertTrue(
            result.getOutput().contains(
                "Policy: Java 17 / UTF-8"
            )
        );
    }
}
~~~

`withPluginClasspath()` dùng plugin-under-test classpath được `java-gradle-plugin` chuẩn bị cho TestKit; fixture áp ID trong `plugins {}` và chạy thật. TestKit có dependency theo plugin-development conventions; test framework JUnit cần được khai báo như trong build logic file ở trên.

Chạy:

~~~bash
./gradlew -p build-logic test validatePlugins --console=plain
~~~

`test` chạy JUnit functional test. `validatePlugins` có thể phát hiện các vấn đề task/plugin metadata khi xây plugin; nó không thay functional testing. Expected result là test pass và fixture task tạo dòng log đã assert. Gradle task logs khác nhau theo version/OS.

### 18.2. Vì sao testkit tốt hơn chỉ test apply?

TestKit có thể phát hiện:

- Plugin ID/descriptor không resolve được.
- `implementationClass` sai package.
- Task không được register hoặc name sai.
- Configuration exception khi Gradle apply plugin.
- Gradle/Java compatibility issues.
- Runtime issues khi task action chạy.
- Configuration Cache problems nếu test fixture dùng thêm `--configuration-cache`.

Với binary plugin phát hành nhiều teams, có thể dùng `GradleRunner.withGradleVersion(...)` để thử các Gradle versions nằm trong ma trận hỗ trợ. Không giả định một lần pass trên Gradle 9.x đồng nghĩa hỗ trợ Gradle 8.x hoặc 10.x.

## 19. Custom extension và managed properties

Một binary plugin có nhiều giá trị cấu hình cần **extension**. Ví dụ file Java (mảnh nâng cao, không thuộc binary plugin tối thiểu):

~~~java
package dev.acme.buildlogic;

import org.gradle.api.provider.Property;

public abstract class BuildPolicyExtension {
    public abstract Property<Integer> getJavaRelease();
}
~~~

Trong `JavaPolicyPlugin.apply`, có thể thêm:

~~~java
BuildPolicyExtension extension =
        project.getExtensions().create(
            "buildPolicy",
            BuildPolicyExtension.class
        );

extension.getJavaRelease().convention(17);
~~~

Sau đó module có thể cấu hình:

~~~kotlin
buildPolicy {
    javaRelease.set(21)
}
~~~

**Đây là các mảnh minh họa**, muốn Java compile target thật đổi theo giá trị extension thì còn phải wire Provider tới toolchain/JavaCompile properties và kiểm thử khi modules override. Đừng hiểu rằng chỉ tạo extension `javaRelease` đã khiến `options.release` tự cập nhật. Khi muốn override default, `convention(17)` phù hợp hơn việc hard-code/set vào nhiều nơi.

## 20. Configuration Cache và build logic

**Configuration Cache** lưu task graph/configured state để tránh chạy lại configuration phase nếu inputs không đổi. **Build Cache** lưu task outputs theo inputs/cache key. **Dependency Cache** lưu downloaded artifacts/metadata. Chúng khác nhau.

Thay đổi plugin code trong `build-logic` có thể khiến Gradle recompile plugin, invalid configuration cache của những projects áp dụng plugin đó và làm tasks cần chạy lại nếu configuration/compiler options thay. Included build không loại bỏ chi phí này hoàn toàn.

### 20.1. Kiểm tra configuration cache

Phương án A:

~~~bash
./gradlew :library:test --configuration-cache --console=plain
./gradlew :library:test --configuration-cache --console=plain
~~~

Trong môi trường hỗ trợ, lượt sau có thể reuse cache entry. Không đảm bảo mỗi lượt đều hit (inputs, environment, Gradle version và task requests có thể khác). Nếu lỗi, đọc configuration-cache report và sửa task/plugin design.

### 20.2. Anti-pattern

- Dùng `Project`/`Gradle`/`Settings` objects trong task action.
- Capture extension sống, closure tùy tiện hoặc environment state không model thành input.
- Dùng `afterEvaluate` để chạy logic vốn có thể dùng Providers/plugin APIs.
- Resolve configurations eager trong plugin apply mà không cần.
- Ghi file/network tại configuration time không theo dõi inputs.
- Dùng `tasks.create(...)` cho hàng loạt task khi có thể `register`.
- Cross-project configuration `subprojects` lồng sâu.
- Đọc secrets qua task action và ghi chúng vào logs.
- Cho nhiều convention plugins ghi đè cùng một property không có owner.

Ưu tiên `tasks.register`, `tasks.named`, `configureEach`, `Provider<T>`, `Property<T>`, các annotations `@Input`, `@OutputFile`, `@InputFiles` cho custom tasks. Cần tránh dùng Gradle internal APIs nếu plugin được kỳ vọng hoạt động qua nhiều Gradle versions.

## 21. IDE sync và troubleshooting

Khi thêm/đổi `build-logic` source, IDE có thể chưa đồng bộ plugin descriptors hoặc type-safe accessors:

1. Kiểm tra root Settings đã đăng ký included build đúng.
2. Kiểm tra `build-logic/settings.gradle.kts` và plugin repositories riêng.
3. Chạy Gradle CLI để tách lỗi IDE khỏi lỗi Gradle thật.
4. Nếu CLI pass mà IDE fail, reload Gradle project/đồng bộ Wrapper và Gradle JVM.
5. Nếu CLI fail, chạy `--stacktrace` để phân biệt plugin source compile lỗi hay plugin resolution lỗi.

Lệnh gợi ý:

~~~bash
./gradlew -p build-logic build --stacktrace --console=plain
./gradlew :library:help --stacktrace --console=plain
./gradlew :library:test --info --console=plain
~~~

`library:help` có thể kiểm tra plugin application/configuration trước khi compile Java. Nếu không tìm thấy plugin ID, xem `pluginManagement.includeBuild` và tên file/ID trước khi sửa Java code.

### 21.1. Các lỗi điển hình

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `Plugin [id: 'acme.java-library-conventions'] was not found` | `pluginManagement.includeBuild` thiếu/sai path | Sửa root Settings, kiểm tra plugin ID từ filename |
| `Could not resolve kotlin-dsl` | Plugin repositories trong included build thiếu/bị chặn | Kiểm tra build-logic Settings và mirror |
| `Unresolved reference: java` | `java-library` không apply trong precompiled `plugins` block hoặc accessor chưa có | Apply plugin đúng thời điểm, dùng typed API |
| `Unresolved reference: testImplementation` | Java/Test configurations chưa có | Apply Java plugin trước, kiểm tra script scope |
| External plugin not found | Plugin implementation JAR thiếu khỏi build-logic dependency classpath | Thêm artifact và version đúng vào build-logic |
| Có repository ở root nhưng build-logic không resolve | Included build không thừa kế repositories | Cấu hình build logic repositories riêng |
| `libs` không tồn tại trong build-logic | Root Version Catalog không tự chuyển sang included build | Import catalog rõ vào build-logic Settings |
| `Plugin ... already on classpath with unknown version` | Trộn version/marker với plugin đã ở classpath | Chọn một owner cho plugin versions |
| JDK toolchain 17 không tìm được | JDK chưa cài hoặc resolver chưa thiết lập | Provision Java 17 đúng máy/CI |
| Test task chạy nhưng không có JUnit engine | Chưa thêm JUnit dependencies/launcher | Khai báo testImplementation/testRuntimeOnly |
| Source compile Java 11 thay vì 17 | Convention plugin không được áp hoặc config bị ghi đè | Kiểm tra toolchain, compile task options |
| `:build-logic` không phải subproject | Đây là included build, không phải include(":...") | Chạy `-p build-logic` |
| TestKit fixture không tìm thấy plugin | Sai `gradlePlugin` ID hoặc `withPluginClasspath` thiếu | Sửa implementationClass/descriptor/TestKit |
| `validatePlugins` báo lỗi | Typed task annotations/metadata không hợp lệ | Sửa task type và input/output declarations |
| Configuration Cache fail vì Project reference | Task action giữ live Project/extension | Dùng managed properties/Providers |
| Plugin code thay nhưng IDE vẫn báo cũ | IDE sync/cache/Gradle JVM | Gradle CLI và reload project |
| Plugin classpath phụ thuộc phiên bản không tương thích | Gradle/JDK/API version mismatch | Pin plugin versions và test compatibility |
| Plugin policy bị áp lên mọi module | `subprojects`/root mutation ngoài ý muốn | Chuyển sang plugins apply tường minh |
| CI build logic fail nhưng local pass | Wrapper, credentials, repositories, JDK khác | So cấu hình build logic độc lập với root |
| Binary plugin được publish nhưng consumer không tìm thấy marker | Chưa có plugin marker publication | Dùng plugin development + publishing đúng |
| Task chạy nhưng console thiếu output | Logger level hoặc task up-to-date/skipped | Xem task outcome và logging configuration |

### 21.2. Quy trình chẩn đoán

1. Đọc lỗi là **plugin resolution**, **script compilation**, **configuration** hay **task execution**.
2. Xem file path `build-logic` từ root Settings; không đọc nhầm folder khác.
3. Xác nhận plugin ID trùng filename hoặc `gradlePlugin.plugins.id`.
4. Build plugin project riêng trước: `./gradlew -p build-logic build`.
5. Kiểm tra repositories của đúng build và plugin classpath dependencies.
6. Chạy `./gradlew :library:help` để thấy module configure được chưa.
7. Sau đó chạy `:library:test` để xác minh Java/tests.
8. Với binary plugin, chạy TestKit và `validatePlugins`.
9. Với cache issues, chạy `--configuration-cache` và đọc problems report.
10. Khi local/CI khác, so Wrapper/JDK/Gradle JVM/credentials/mirrors.

Không chữa lỗi bằng việc tắt quality gate, copy plugin JAR không rõ nguồn hoặc ép `subprojects` apply một bản plugin khác mà không biết nguồn.

## 22. Phát hành binary plugin cho nhiều repositories

Nếu một plugin cần được dùng trong **nhiều source repositories không thuộc cùng monorepo**, có thể publish binary plugin lên Maven artifact repository/Gradle Plugin Portal có kiểm soát.

Với phương án B đã đăng ký:

~~~kotlin
gradlePlugin {
    plugins {
        create("javaPolicy") {
            id = "acme.java-policy"
            implementationClass =
                "dev.acme.buildlogic.JavaPolicyPlugin"
        }
    }
}
~~~

có thể tích hợp plugin `maven-publish` để Gradle tạo plugin publication metadata (implementation artifact và plugin marker) theo cơ chế Java Gradle Plugin Development plugin.

Consumers ngoài repo có thể dùng:

~~~kotlin
plugins {
    id("acme.java-policy") version "1.0.0"
}
~~~

Đây là **cú pháp khi plugin đã được publish và repository/marker được cấu hình**, khác với local included build không cần version.

### 22.1. Plugin marker là gì?

Modern Gradle `plugins { id(...) version(...) }` cần ánh xạ **plugin ID/version** tới implementation module. Plugin marker artifacts làm nhiệm vụ đó. Chỉ upload một implementation JAR không bảo đảm plugins DSL tìm được ID nếu không có marker hoặc explicit plugin resolution strategy.

### 22.2. CI/release policy của binary plugin

- Pin plugin version và Gradle/JDK compatibility.
- Chạy unit/functional tests bằng TestKit trên versions hỗ trợ.
- Giữ published versions immutable.
- Không hard-code repository credentials.
- Xác nhận plugin marker và implementation artifacts đều có trong staging repository.
- Dùng một project consumer **độc lập** để kiểm tra `plugins { id(...) version(...) }` từ đúng repository.
- Không lẫn build plugin dependencies với production application dependencies.
- Đảm bảo license/security review các Gradle plugin artifacts và transitive dependencies.

Nếu plugin chỉ phục vụ một monorepo và được thay đổi cùng ứng dụng, included build thường đơn giản hơn việc publish mỗi lần sửa.

## 23. CI: kiểm tra build-logic trước modules

Phương án A:

~~~bash
set -e
./gradlew -p build-logic build --console=plain
./gradlew :library:clean :library:test --console=plain
./gradlew :library:jar --console=plain
~~~

Phương án B:

~~~bash
set -e
./gradlew -p build-logic test validatePlugins --console=plain
./gradlew :library:printJavaPolicy --console=plain
~~~

**Không dùng cả hai lệnh trên trong cùng một build-logic config nếu chưa chuyển plugin IDs**. Chúng là hai triển khai độc lập cho mục đích học tập.

Kiểm tra task graph:

~~~bash
./gradlew :library:test --dry-run --console=plain
~~~

Lệnh chỉ cho biết tasks được chọn, không thực thi JUnit tests. Khi CI yêu cầu build logic confidence, phải thực sự chạy tests, không dùng `--dry-run` làm bằng chứng.

### 23.1. Testing matrix

Một plugin nội bộ có thể chỉ hỗ trợ một Gradle Wrapper version trong repo. Nếu publish cho nhiều repos, test các Gradle/JDK versions được hỗ trợ chính thức, không suy luận Gradle 9 plugin chạy trên Gradle 8 hoặc Gradle 10.

### 23.2. Security

Gradle plugin có thể thực thi mã trong build/CI, nên kiểm soát plugin repositories, artifact verification và credentials. Không đưa access token vào source hoặc log. Khi plugin dùng secret để truy cập repository, truyền qua Gradle Providers/secret store theo policy và tránh giữ secret ở task state không cần thiết.

## 24. Bài tập và đáp án

**Câu 1.** Vì sao cần `pluginManagement { includeBuild("build-logic") }` trong root Settings?

**Đáp án:** Để plugin IDs do included build tạo ra tham gia plugin resolution của modern `plugins {}` DSL.

**Câu 2.** `include(":build-logic")` có thay `includeBuild("build-logic")` không?

**Đáp án:** Không. Một bên là subproject, một bên là included Gradle build độc lập.

**Câu 3.** Filename `acme.java-library-conventions.gradle.kts` sinh plugin ID gì?

**Đáp án:** `acme.java-library-conventions` nếu không có package declaration.

**Câu 4.** Precompiled Kotlin DSL script plugin cần gì trong build-logic build file?

**Đáp án:** `plugins { `kotlin-dsl` }` và repositories/dependencies thích hợp.

**Câu 5.** Dùng `useJUnitPlatform()` đã đủ chạy JUnit Jupiter test chưa?

**Đáp án:** Chưa. Cần JUnit Jupiter dependencies, test engine và launcher ở test runtime.

**Câu 6.** Java Library plugin có được áp lại ở module không?

**Đáp án:** Không cần, vì convention plugin đã apply `java-library`.

**Câu 7.** Plugin build repositories có tự thừa kế root repositories không?

**Đáp án:** Không. Included build có Settings/dependencies riêng.

**Câu 8.** Root `libs` Version Catalog có tự xuất hiện trong build-logic không?

**Đáp án:** Không, cần import/khai báo nếu dùng.

**Câu 9.** Tại sao không đặt `version "..."` trong `plugins` block của precompiled script plugin?

**Đáp án:** Cú pháp version/apply false không được hỗ trợ ở đó; external plugin implementation version phải được xác định qua build-logic dependencies.

**Câu 10.** Type-safe accessor `java {}` có xuất hiện khi apply `java-library` chỉ bằng `apply(plugin=...)` trong script body không?

**Đáp án:** Không bảo đảm như khi plugin nằm trong `plugins` block; dùng APIs typed khi cần.

**Câu 11.** `GradleRunner.withPluginClasspath()` để làm gì?

**Đáp án:** Cho TestKit fixture dùng implementation classpath của plugin đang được test để có thể apply plugin ID.

**Câu 12.** Tại sao custom task không nên giữ Project trong task action?

**Đáp án:** Vi phạm các quy tắc Configuration Cache/isolated task state; nên model inputs/outputs qua Providers.

**Câu 13.** Khi nào nên viết binary plugin bằng Java?

**Đáp án:** Khi cần typed task, extension/managed properties, logic phức tạp hoặc muốn publish plugin qua nhiều repos.

**Câu 14.** `buildSrc` khác included `build-logic` thế nào?

**Đáp án:** buildSrc được Gradle tự nhận diện; build-logic phải khai báo includeBuild và có thể test/tổ chức độc lập.

**Câu 15.** `java -cp library/build/classes/java/main demo.Greeting` in gì?

**Đáp án:** Một dòng `Xin chào, Lan!` theo source Java trong bài.

**Câu 16.** Chỉ upload binary plugin JAR là đủ cho consumer `plugins { id("acme.java-policy") version "1.0.0" }` chưa?

**Đáp án:** Không luôn đủ; cần plugin marker metadata hoặc plugin resolution strategy tương ứng.

**Câu 17.** `--dry-run` có chứng minh test pass không?

**Đáp án:** Không, nó không thực thi task actions.

**Câu 18.** Thay convention plugin code có chắc Configuration Cache hit không?

**Đáp án:** Không; code/configuration inputs đổi có thể làm cache invalid.

## 25. Checklist ứng dụng thực tế

1. Tạo `build-logic` như một Gradle build riêng.
2. Đặt `pluginManagement.includeBuild("build-logic")` ở root Settings.
3. Dùng `kotlin-dsl` cho precompiled script plugins.
4. Dùng `java-gradle-plugin`/`Plugin<Project>` cho binary plugins.
5. Chọn plugin IDs ổn định, không trùng Gradle core.
6. Tách các conventions theo Java base/library/application/testing/quality/publishing.
7. Để modules tự apply plugin trong `plugins {}`.
8. Đặt Java toolchain/encoding/release rõ ràng và kiểm tra với Gradle.
9. Khai báo test dependencies riêng hoặc trong đúng testing convention plugin.
10. Dùng lazy configuration APIs và managed properties.
11. Phân biệt root plugin repos, included build deps repos và app repos.
12. Import version catalog vào included build nếu cần.
13. Không trộn plugin classpath với app runtime classpath.
14. Test plugin riêng; dùng Gradle TestKit cho functional tests.
15. Kiểm tra `--configuration-cache` và Gradle/JDK version matrix.
16. Tránh `subprojects` cross-project policy và `afterEvaluate` thiếu cần thiết.
17. Quản lý external plugin versions/capabilities theo chính sách.
18. Khi publish binary plugin, publish cả marker metadata và implementation.
19. Đừng lưu secrets trong source/logs.
20. Giữ CI quality gate cho plugin và module consumers.

**Tóm tắt:**

~~~text
Root settings.gradle.kts
   pluginManagement.includeBuild("build-logic")
             |
             v
build-logic (independent build)
   kotlin-dsl -> precompiled .gradle.kts plugin
      hoặc
   java-gradle-plugin -> binary Plugin<Project>
             |
             v
:library plugins { id("acme.java-library-conventions") }
             |
             v
Java Library plugin + Java 17 policy + JUnit Platform
             |
             v
compileJava / test / jar

include(":build-logic") != includeBuild("build-logic")
Plugin classpath != application runtimeClasspath
buildSrc auto-detected != build-logic explicitly included
~~~

## 26. Tài liệu chính thức

1. Gradle — Sharing Build Logic between Subprojects: https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html
2. Gradle — Composite Builds (Included Builds): https://docs.gradle.org/current/userguide/composite_builds.html
3. Gradle — Precompiled Script Plugins: https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html
4. Gradle — Advanced Precompiled Script Plugins: https://docs.gradle.org/current/userguide/pre_compiled_script_plugin_advanced.html
5. Gradle — Introduction to Plugins: https://docs.gradle.org/current/userguide/plugins.html
6. Gradle — Implementation Options for Plugins: https://docs.gradle.org/current/userguide/implementing_gradle_plugins.html
7. Gradle — Binary Plugins: https://docs.gradle.org/current/userguide/writing_plugins.html
8. Gradle — Gradle TestKit: https://docs.gradle.org/current/userguide/test_kit.html
9. Gradle — Testing Plugins: https://docs.gradle.org/current/userguide/testing_gradle_plugins.html
10. Gradle — Kotlin DSL Primer/Type-safe Accessors: https://docs.gradle.org/current/userguide/kotlin_dsl.html
11. Gradle — Configuration Cache: https://docs.gradle.org/current/userguide/configuration_cache.html
12. Gradle — Configuration Cache Requirements: https://docs.gradle.org/current/userguide/configuration_cache_requirements.html
13. Gradle — Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
14. Gradle — Writing Custom Tasks: https://docs.gradle.org/current/userguide/implementing_custom_tasks.html
15. Gradle — Publishing Gradle Plugins: https://docs.gradle.org/current/userguide/publishing_gradle_plugins.html

**Phiên bản và phạm vi:** Các đường dẫn `/current/` là tài liệu hiện hành, có thể không trùng Gradle Wrapper của dự án. Khi áp dụng thực tế, kiểm tra yêu cầu JDK, plugin APIs và version compatibility theo Wrapper. Mẫu precompiled plugin và binary plugin là **hai phương án độc lập**, không phải hai script được dán chồng vào cùng `build-logic/build.gradle.kts`.
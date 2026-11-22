# Tổng hợp báo cáo và artifact mà không làm mất ranh giới module — Build nhiều dự án với Gradle

## 1. Bài toán và mục tiêu

Trong một hệ thống **Build nhiều dự án** (*Gradle multi-project build*), những module như `:core`, `:app`, `:web` và `:data` được xây dựng độc lập về source sets, dependencies, tasks và outputs. Tuy nhiên, một nhóm kỹ thuật vẫn cần nhìn **toàn bộ sản phẩm**: tất cả tests đã chạy chưa, coverage toàn hệ thống ra sao, các JAR nào cần bàn giao, CI sẽ lưu những report/artifact nào.

Nguy cơ xuất hiện khi root project cố gắng đọc và sửa mọi thứ của các module:

- Root copy toàn bộ `*/build/libs/*` rồi vô tình gom artifact cũ, source JAR, Javadoc JAR hoặc trùng tên.
- Hai modules cùng ghi `root/build/reports/test/index.html` dẫn tới ghi đè/race.
- Root truy cập `project(':core').tasks`, `project(':app').layout` khi configuration, làm các projects gắn chặt với nhau và có thể vi phạm **Isolated Projects**.
- Một task dùng `dependsOn ':core:jar'` nhưng tự đọc file path đoán trước, không khai data input để Gradle quản lý.
- CI copy nhiều HTML sites vào một folder rồi gọi đó là “test report tổng hợp”, trong khi các `index.html`/CSS paths đã đè lên nhau.
- Một test thất bại nhưng pipeline chỉ thấy file report tồn tại và cho deploy.

**Nguyên tắc trung tâm:** **Module vẫn là chủ sở hữu nguồn, kết quả test và artifact.** Một project chuyên trách aggregation có quyền **tiêu thụ những outputs đã được module công bố qua hợp đồng**, rồi tạo output của chính mình; root chỉ điều phối lifecycle tasks khi không cần dữ liệu.

### 1.1. Ba loại tổng hợp

| Việc cần làm | Ví dụ | Mô hình Gradle thích hợp |
| --- | --- | --- |
| **Điều phối** | Chạy `:core:check` và `:app:check` | Root task `dependsOn ':core:check', ':app:check'` |
| **Thu artifact** | Lấy JAR binary từ `:core` và `:app`, tạo ZIP | Incoming resolvable configuration + outgoing Java variants/project dependencies |
| **Gộp dữ liệu report** | HTML test report chung hoặc JaCoCo coverage toàn hệ thống | `test-report-aggregation` hoặc `jacoco-report-aggregation` plugin |
| **Tập hợp report sites** | Lưu HTML Checkstyle của từng module | Giữ namespace `core/`, `app/` và tạo index link; không giả vờ đã merge dữ liệu |

**Task ordering không đồng nghĩa data dependency.** `dependsOn` chỉ đảm bảo tác vụ trước/sau. Khi một task thực sự **đọc output** từ task khác, Gradle cần biết **file collection/variant/input** ấy là gì và task nào sản xuất nó.

### 1.2. Học xong bạn làm được gì?

1. Hiểu project path, task path, source/output ownership trong multi-project build.
2. Tạo root lifecycle task để chạy quality checks mà không sửa module.
3. Dùng `runtimeElements` và variant attributes để gom đúng binary JARs của các module.
4. Dùng `test-report-aggregation` tạo HTML test report hợp nhất từ các test-result variants.
5. Phân biệt test results với JaCoCo execution data, không tính coverage tổng bằng trung bình phần trăm.
6. Chạy một **ví dụ Java 17, Gradle Groovy DSL hoàn chỉnh** có hai modules Java và hai modules aggregator.
7. Kiểm tra stdout, JAR contents, report ownership, duplicate paths và CI failure behavior.
8. Nhận biết cross-project coupling, data dependencies bị thiếu, cache/parallel/race issues.

## 2. Nắm ranh giới của multi-project build

Dự án mẫu có cấu trúc:

~~~text
multi-evidence/
├── settings.gradle
├── build.gradle                   (root: lifecycle aggregation)
├── core/
│   ├── build.gradle
│   └── src/
├── app/
│   ├── build.gradle
│   └── src/
├── bundle/
│   └── build.gradle              (artifact aggregation)
├── reports/
│   └── build.gradle              (test report aggregation)
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
~~~

Trong `settings.gradle`:

~~~groovy
rootProject.name = 'multi-evidence'
include 'core', 'app', 'bundle', 'reports'
~~~

Project paths chính xác là `:core`, `:app`, `:bundle`, `:reports`. Mỗi project có:
- File `build.gradle` độc lập.
- `tasks` và `configurations` thuộc phạm vi project đó.
- `layout.projectDirectory` và `layout.buildDirectory` riêng.
- Source/resources/test conventions riêng.
- Quyền quyết định output nào **được xuất ra ngoài** qua consumable configuration/variant.

Từ Gradle 9.0, những subproject directories được `include` phải tồn tại và có thể ghi khi build chạy; không khai `include 'ghost'` nếu thư mục `ghost/` chưa được tạo.

### 2.1. Module ownership

| Module | Sở hữu gì? | Output điển hình |
| --- | --- | --- |
| `:core` | Java library, tests, Java component | `core/build/libs/core-1.0.0.jar`, `core/build/test-results/test` |
| `:app` | Java application, tests, dependency vào core | `app/build/libs/app-1.0.0.jar`, `app/build/test-results/test` |
| `:bundle` | Chính sách bàn giao JAR và ZIP | `bundle/build/distribution/libs`, `bundle/build/archives/module-jars-1.0.0.zip` |
| `:reports` | Chính sách tổng hợp test results | HTML dưới `reports/build/reports` theo plugin/task |
| Root `:` | Orchestrating named lifecycle tasks | Không sở hữu lại class/test reports/JAR gốc |

**Không cho hai project cùng ghi một output directory.** Gradle up-to-date checking/build cache/parallel execution khó chính xác nếu các tasks khác project cùng sửa một tập files mà không có owner rõ.

## 3. Root làm orchestration, không làm “siêu module”

Với nhu cầu đơn giản là kiểm tra tất cả modules:

~~~groovy
plugins {
    id 'base'
}

tasks.register('verifyModules') {
    group = 'verification'
    description = 'Run checks owned by core and app'
    dependsOn ':core:check', ':app:check'
}
~~~

Khi chạy:

~~~bash
./gradlew verifyModules
~~~

Gradle thực thi `:core:check` và `:app:check` cùng dependencies như `test`/static analysis nếu được cấu hình. Root **không đọc** XML reports hoặc JARs, nên dependency theo task path là đủ.

Gradle Isolated Projects cho phép tham chiếu **task path** từ module khác khi nó chỉ là **orchestration dependency**. Tuy nhiên, nó không cho phép truy cập mutable state của project khác như:

~~~groovy
// Chống chỉ định trong root aggregator:
project(':core').tasks.named('jar')
project(':app').configurations.runtimeClasspath
project(':core').layout.buildDirectory
~~~

Đó là direct cross-project access, có thể vi phạm Isolated Projects hoặc gây coupling khiến configuration cache, configuration on demand và parallel configuration khó hoạt động.

### 3.1. `dependsOn` không tự khai file inputs

Đoạn sau là **anti-pattern**:

~~~groovy
tasks.register('mergeAll') {
    dependsOn ':core:jar', ':app:jar'

    doLast {
        // Sai: tự đoán output paths của project khác.
        copy {
            from 'core/build/libs'
            from 'app/build/libs'
            into 'build/all'
        }
    }
}
~~~

Nó có thể chạy được tạm thời nhưng thiếu hợp đồng file inputs, output ownership/variants, dễ copy file cũ và có thể ghi đè tên JAR trùng. `dependsOn` chỉ đảm bảo task order, không thay thế data dependency.

### 3.2. Không sửa tất cả subprojects từ root

Một pattern cũ:

~~~groovy
subprojects {
    apply plugin: 'java'
    tasks.named('test') {
        // Root trực tiếp sửa cấu hình project con.
    }
}
~~~

Gradle vẫn cho phép một số kiểu cross-project configuration ở chế độ thông thường, nhưng hướng thiết kế bền vững hơn là **module tự cấu hình mình** hoặc dùng **convention plugin** áp tại module. Root không cần biết chi tiết private tasks/plugins của mọi module.

## 4. Hai kiểu phụ thuộc cần phân biệt

### 4.1. Java project dependency

Trong `app/build.gradle`:

~~~groovy
dependencies {
    implementation project(':core')
}
~~~

Điều này tạo compile/runtime dependency từ app đến core. Gradle chọn variants của core, thêm classes/JAR và transitive dependencies phù hợp vào classpath app. Khi `:app:compileJava` chạy, Gradle xây các outputs cần thiết của core trước.

### 4.2. Artifact dependency để đóng gói

`:bundle` không compile app; nó cần **files** do modules tạo ra. Dùng project dependencies vào một configuration riêng, kèm attributes:
- `Usage.JAVA_RUNTIME`.
- `Category.LIBRARY`.
- `LibraryElements.JAR`.

Gradle giải quyết các **outgoing variants** `runtimeElements`/Java component tương thích, biết producer task nào tạo binary JAR. Không hard-code `../core/build/libs/core-1.0.0.jar` làm input.

Có thể quan sát các variants với:

~~~bash
./gradlew :core:outgoingVariants
./gradlew :app:outgoingVariants
~~~

Thông tin thường gồm `org.gradle.usage`, `org.gradle.category`, `org.gradle.libraryelements`, JVM target version, artifacts. Đây là mô hình rõ ràng cho **data flow qua module boundary**.

### 4.3. Báo cáo test cũng có outgoing variants

Java plugin/JVM Test Suite Plugin xuất **binary test-result artifacts** cho từng suite. `test-report-aggregation` chọn các result variants có:
- `org.gradle.category = verification`.
- `org.gradle.testsuite.name = test`.
- `org.gradle.verificationtype = test-results`.

Nhờ đó `:reports` không phải đọc `../core/build/reports/tests/test/index.html`. Plugin dựng một HTML summary từ **test results**, không copy/mashup HTML thủ công.

## 5. Bài thực hành trọn vẹn: Java 17, JUnit 5, bốn Gradle projects

Bài lab gồm:
- `:core` tạo Java library `Greeter` và một JUnit test.
- `:app` tạo Java program `Main` dùng Greeter và một JUnit test.
- `:bundle` tạo distribution folder và ZIP chứa **hai binary JAR**.
- `:reports` sinh aggregated HTML test report từ **hai tests**.
- Root tạo tasks `verifyModules`, `collectEvidence`, `releaseEvidence`.

**Môi trường:** Gradle Wrapper tương thích JDK 17 và JVM Test Suite/Test Report Aggregation APIs, Java 17 cài sẵn hoặc toolchain có thể tìm JDK 17. JUnit Jupiter 5.11.4 và launcher 1.11.4 cần có trong cache hoặc tải từ Maven Central. Không có server publish/deploy ở lab.

### 5.1. Cấu trúc cụ thể

~~~text
multi-evidence/
├── settings.gradle
├── build.gradle
├── core/
│   ├── build.gradle
│   ├── src/main/java/dev/demo/core/Greeter.java
│   └── src/test/java/dev/demo/core/GreeterTest.java
├── app/
│   ├── build.gradle
│   ├── src/main/java/dev/demo/app/Main.java
│   └── src/test/java/dev/demo/app/MainTest.java
├── bundle/
│   └── build.gradle
├── reports/
│   └── build.gradle
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
~~~

Nếu chưa có Wrapper, dùng bản Gradle đã cài tương thích để tạo `gradle wrapper` rồi lưu đầy đủ bộ Wrapper vào repository. Tạo đủ bốn project directories trước khi chạy.

### 5.2. `settings.gradle`

~~~groovy
rootProject.name = 'multi-evidence'
include 'core', 'app', 'bundle', 'reports'
~~~

### 5.3. Root `build.gradle`

~~~groovy
plugins {
    id 'base'
}

tasks.register('verifyModules') {
    group = 'verification'
    description = 'Run checks of core and app'
    dependsOn ':core:check', ':app:check'
}

tasks.register('collectEvidence') {
    group = 'distribution'
    description = 'Produce archive and aggregate HTML report'
    dependsOn ':bundle:packJars', ':reports:testAggregateTestReport'
}

tasks.register('releaseEvidence') {
    group = 'verification'
    description = 'Verify modules and produce evidence artifacts'
    dependsOn tasks.named('verifyModules'), tasks.named('collectEvidence')
}
~~~

Root tasks là **orchestrators**, không có `doLast` đọc source hoặc output của modules khác. `collectEvidence` không merge HTML/JAR vào root; nó điều phối hai specialized aggregation tasks có output owners riêng.

### 5.4. `core/build.gradle`

~~~groovy
plugins {
    id 'java-library'
}

group = 'dev.demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`java-library` sở hữu Java component và `runtimeElements`. JUnit chỉ là **test dependency**, không thuộc binary runtime JAR. Java Toolchain 17 kết hợp `options.release=17` đảm bảo target Java 17 và `options.encoding` cho source UTF-8.

### 5.5. `core/src/main/java/dev/demo/core/Greeter.java`

~~~java
package dev.demo.core;

/** Shared greeting API. */
public final class Greeter {

    private Greeter() {
    }

    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

### 5.6. `core/src/test/java/dev/demo/core/GreeterTest.java`

~~~java
package dev.demo.core;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class GreeterTest {

    @Test
    void greetsTheRecipient() {
        assertEquals("Hello, Gradle!", Greeter.greet("Gradle"));
    }
}
~~~

### 5.7. `app/build.gradle`

~~~groovy
plugins {
    id 'application'
}

group = 'dev.demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation project(':core')
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

application {
    mainClass = 'dev.demo.app.Main'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`application` áp Java plugin, tạo `run`; `implementation project(':core')` là **runtime/compile dependency** hợp lệ và mô tả app dùng library core. Không dùng absolute path hoặc file source của core.

### 5.8. `app/src/main/java/dev/demo/app/Main.java`

~~~java
package dev.demo.app;

import dev.demo.core.Greeter;

public final class Main {

    private Main() {
    }

    public static String message() {
        return Greeter.greet("modules");
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Chạy:

~~~bash
./gradlew :app:run --quiet
~~~

**Stdout chính xác của Java application** (bỏ qua thông báo Gradle):

~~~text
Hello, modules!
~~~

### 5.9. `app/src/test/java/dev/demo/app/MainTest.java`

~~~java
package dev.demo.app;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class MainTest {

    @Test
    void applicationUsesCore() {
        assertEquals("Hello, modules!", Main.message());
    }
}
~~~

Khi test sources và dependencies được giải quyết thành công, hai modules có tổng cộng **hai JUnit tests**:
- `:core:GreeterTest.greetsTheRecipient`.
- `:app:MainTest.applicationUsesCore`.

Mỗi task `test` vẫn sở hữu binary results/HTML reports của module tương ứng. Không đặt cả hai task outputs vào shared root directory.

## 6. `:bundle`: gom JAR qua resolvable configuration thay vì cross-project task access

### 6.1. Toàn bộ `bundle/build.gradle`

~~~groovy
import org.gradle.api.attributes.Category
import org.gradle.api.attributes.LibraryElements
import org.gradle.api.attributes.Usage
import org.gradle.api.file.DuplicatesStrategy

plugins {
    id 'base'
}

configurations {
    moduleJars {
        canBeResolved = true
        canBeConsumed = false

        // Chỉ lấy hai modules trực tiếp, tránh kéo dependencies bắc cầu.
        transitive = false

        attributes {
            attribute(
                Usage.USAGE_ATTRIBUTE,
                objects.named(Usage, Usage.JAVA_RUNTIME)
            )
            attribute(
                Category.CATEGORY_ATTRIBUTE,
                objects.named(Category, Category.LIBRARY)
            )
            attribute(
                LibraryElements.LIBRARY_ELEMENTS_ATTRIBUTE,
                objects.named(LibraryElements, LibraryElements.JAR)
            )
        }
    }
}

dependencies {
    moduleJars project(':core')
    moduleJars project(':app')
}

tasks.register('collectJars', Sync) {
    group = 'distribution'
    description = 'Copy declared Java runtime JAR artifacts'

    from(configurations.moduleJars)
    into(layout.buildDirectory.dir('distribution/libs'))
    duplicatesStrategy = DuplicatesStrategy.FAIL
}

tasks.register('packJars', Zip) {
    group = 'distribution'
    description = 'Archive collected module JARs'

    from(tasks.named('collectJars')) {
        into 'libs'
    }

    destinationDirectory = layout.buildDirectory.dir('archives')
    archiveFileName = 'module-jars-1.0.0.zip'
    duplicatesStrategy = DuplicatesStrategy.FAIL

    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

### 6.2. Phân tích configuration

- `moduleJars.canBeResolved=true` cho phép consumer `:bundle` resolve artifacts.
- `canBeConsumed=false` bảo đảm nó **không** được các projects khác tiêu thụ như outgoing variant của bundle.
- `transitive=false` có chủ đích: lab muốn **đúng hai JAR trực tiếp** của core và app, không thêm dependencies bắc cầu. Vì app đã phụ thuộc core, nếu cho transitive, core có thể xuất hiện qua cả app và direct dependency. Mặt khác, nếu app có external runtime dependencies, một distribution dùng `transitive=false` có thể **không đủ để chạy**. Bài lab chỉ có Java standard library và core runtime dependency nên hai JAR là đủ.
- Attributes yêu cầu `java-runtime`, `library`, `jar` để chọn binary Jar variants, tránh source/Javadoc/compiled classes variants không phù hợp.
- `moduleJars project(':core')` và `project(':app')` là **project dependencies**, không tham chiếu trực tiếp task providers của project khác.
- `Sync` tiêu thụ file collection `configurations.moduleJars`; Gradle có dependency/provenance của selected artifacts.
- `Sync.into(layout.buildDirectory.dir(...))` ghi dưới **bundle's own build directory**, không ghi đè outputs producer.
- `DuplicatesStrategy.FAIL` giúp phát hiện collisions giữa filenames thay vì silently discard artifacts.
- `packJars` đọc output `collectJars` qua **task provider trong cùng project**; không cần raw path tới `:core:jar`.
- ZIP options làm archive order/timestamps ổn định; compiled JAR content vẫn cần deterministic compiler/source/generator inputs.

### 6.3. Kết quả dự kiến

~~~bash
./gradlew :bundle:collectJars
./gradlew :bundle:packJars
~~~

Files:

~~~text
bundle/build/
├── distribution/
│   └── libs/
│       ├── core-1.0.0.jar
│       └── app-1.0.0.jar
└── archives/
    └── module-jars-1.0.0.zip
~~~

ZIP có những entries quan trọng:

~~~text
libs/core-1.0.0.jar
libs/app-1.0.0.jar
~~~

Kiểm tra bằng JDK `jar` tool:

~~~bash
jar tf bundle/build/archives/module-jars-1.0.0.zip
~~~

`jar tf` có thể hiển thị thêm directory entries; đừng phụ thuộc vào một thứ tự dòng cụ thể. Quan trọng là đúng hai binary JARs, không có `-sources.jar`, `-javadoc.jar` hay JUnit jars trong gói lab.

### 6.4. Chạy ứng dụng từ JARs đã gom

Linux/macOS, từ root:

~~~bash
java -cp "bundle/build/distribution/libs/app-1.0.0.jar:bundle/build/distribution/libs/core-1.0.0.jar" dev.demo.app.Main
~~~

PowerShell trên Windows (dấu `;` phân tách classpath):

~~~powershell
java -cp 'bundle/build/distribution/libs/app-1.0.0.jar;bundle/build/distribution/libs/core-1.0.0.jar' dev.demo.app.Main
~~~

**Stdout chính xác:**

~~~text
Hello, modules!
~~~

Đây là **bundle nhiều JAR**, không phải fat JAR. Lệnh `java -jar app-1.0.0.jar` không nhất thiết chạy được vì plain Java JAR không tự có executable main manifest và dependency classpath. Nếu cần app distribution cho người dùng cuối, cân nhắc Application plugin distribution, startup scripts hoặc container/image tooling chuyên dụng.

### 6.5. Tại sao không dùng `from('../core/build/libs')`?

Nếu bạn copy nguyên thư mục:
- Có thể bao gồm sources/Javadoc JARs khác classifier.
- Có thể bao gồm file cũ sau khi project đổi version.
- Copy sẽ không tự biết producer task/variant dependency.
- Có thể trùng filename khi modules dùng chung `archiveBaseName`.
- Khi plugin đổi output path, aggregator hỏng.

Một resolvable configuration lấy **outgoing artifacts** theo Gradle model giúp tách “cái gì cần dùng” khỏi “module đã ghi file vào đâu”.

## 7. `:reports`: tạo HTML test report tổng hợp đúng nghĩa

### 7.1. Không copy hai HTML report sites vào chung thư mục

Cả hai modules có thể tạo:

~~~text
core/build/reports/tests/test/index.html
app/build/reports/tests/test/index.html
~~~

Nếu copy file cùng tên vào `reports/build/all/index.html`, bạn sẽ bị overwrite/duplicate handling và hỏng relative CSS/JS assets. Điều đó **không** tạo counts/testcase summary hợp nhất.

Vì Java test results có schema và outgoing variants chuẩn, dùng Gradle `test-report-aggregation` plugin.

### 7.2. `reports/build.gradle` — toàn bộ

~~~groovy
plugins {
    id 'test-report-aggregation'
}

dependencies {
    testReportAggregation project(':core')
    testReportAggregation project(':app')
}

// Standalone aggregator không áp jvm-test-suite.
// Đăng ký report cho suite tên "test".
reporting {
    reports {
        testAggregateTestReport(AggregateTestReport) {
            testSuiteName = 'test'
        }
    }
}
~~~

Gradle plugin tạo configuration `testReportAggregation`, chọn **test-results verification variants** từ `:core`/`:app` và tạo backing task `testAggregateTestReport`.

**Tại sao không gọi `project(':core').tasks.named('test')`?** Bởi vì Gradle biết producers qua outgoing variants và project dependencies, tránh cross-project mutable state reads. `:reports` chỉ khai mình muốn “test results của core và app”, không ép task internals của core/app thành public API.

### 7.3. Chạy report aggregation

~~~bash
./gradlew :reports:testAggregateTestReport
~~~

Khi hai JUnit test tasks PASS, bạn sẽ có HTML report tổng hợp hiển thị **hai tests**, không có failure:
- Test trong `dev.demo.core.GreeterTest`.
- Test trong `dev.demo.app.MainTest`.

Output HTML thường nằm trong `reports/build/reports/...` với report name `testAggregateTestReport`. Tên thư mục cuối có thể khác giữa Gradle versions/report configuration; xem logs/output property thay vì hard-code path cho consumer khác.

**Không khẳng định** stdout Gradle, timings, HTML labels hoặc task order là cố định; chỉ kỳ vọng test counts và nội dung tương ứng với hai tests thực tế.

### 7.4. `--continue` khi test bị lỗi

Nếu một task `test` fail, Gradle mặc định dừng các tasks còn lại theo failure handling. Để thu thêm báo cáo:

~~~bash
./gradlew :reports:testAggregateTestReport --continue
~~~

`--continue` cho phép chạy những tasks có thể tiếp tục, nhưng những tasks bị blocked bởi failed dependencies vẫn có thể không chạy. **Overall build vẫn FAIL** nếu tests fail. Nó không chữa lỗi test và không biến failed suite thành passed suite.

Trên CI nên upload **raw module reports** kể cả khi HTML aggregate không tạo được, phục vụ chẩn đoán. Không nên đặt `ignoreFailures=true` bừa bãi chỉ để lấy báo cáo.

## 8. Root gọi các task đúng vai trò

Với root build đã khai ở phần 5:

~~~bash
./gradlew verifyModules
./gradlew collectEvidence
./gradlew releaseEvidence
~~~

- `verifyModules`: orchestration checks, không tiêu thụ report/JAR data.
- `collectEvidence`: gọi hai aggregators, nhưng chúng tự khai inputs/output ownership.
- `releaseEvidence`: nối hai lifecycle workflows, phù hợp một quality gate.

Kiểm tra từng phần khi debug:

~~~bash
./gradlew :core:test
./gradlew :app:test
./gradlew :bundle:packJars
./gradlew :reports:testAggregateTestReport
./gradlew :app:run --quiet
~~~

Với Java program, stdout ứng dụng là:

~~~text
Hello, modules!
~~~

Các Gradle tasks khác có log phụ thuộc môi trường, cache và JDK, không cần một output text hằng.

### 8.1. Kiểm tra ownership bằng output tree

Sau build:

~~~text
core/build/libs/core-1.0.0.jar
core/build/test-results/test/...
core/build/reports/tests/test/...

app/build/libs/app-1.0.0.jar
app/build/test-results/test/...
app/build/reports/tests/test/...

bundle/build/distribution/libs/core-1.0.0.jar
bundle/build/distribution/libs/app-1.0.0.jar
bundle/build/archives/module-jars-1.0.0.zip

reports/build/reports/.../index.html
~~~

**Không có task aggregator nào được phép xóa/ghi đè `core/build` hoặc `app/build`**. Việc bundle có bản copy của binary JAR là **tạo output mới**, không chuyển ownership của JAR producer.

## 9. Coverage aggregation bằng JaCoCo: phần mở rộng

**Test report khác code coverage report.**

- Test report cho biết tests nào PASS/FAIL/SKIPPED, durations và classes/suites.
- JaCoCo coverage dựa trên binary execution data và class/source definitions, đo covered vs total instructions/branches/lines tùy report.
- Không thể tính coverage toàn hệ thống bằng trung bình số phần trăm coverage của modules. Mẫu số của mỗi module khác nhau.

Gradle `jacoco-report-aggregation` plugin hỗ trợ thu coverage từ nhiều Gradle Java/JVM projects khi các modules đã cung cấp JaCoCo execution data variants.

### 9.1. Mở rộng với `:coverage`

Đây là **snippet mở rộng**, **không phải phần bắt buộc của lab bốn modules**. Muốn thử cần thêm `include 'coverage'` trong `settings.gradle` và tạo project directory `coverage/`.

Trong từng Java producer, áp JaCoCo bên cạnh Java plugin:

~~~groovy
plugins {
    id 'jacoco'
}
~~~

Giữ các JUnit tests như trong lab. Trong `coverage/build.gradle`:

~~~groovy
plugins {
    id 'jacoco-report-aggregation'
}

dependencies {
    jacocoAggregation project(':core')
    jacocoAggregation project(':app')
}

reporting {
    reports {
        testCodeCoverageReport(JacocoCoverageReport) {
            testSuiteName = 'test'
        }
    }
}
~~~

Chạy:

~~~bash
./gradlew :coverage:testCodeCoverageReport
~~~

Với standalone aggregation project, report type được đăng ký thủ công. Dữ liệu được chọn từ `jacoco-results` verification variants của producer. Chỉ áp `jacoco-report-aggregation` ở consumer mà producer không tạo execution data thì không có coverage thực sự để merge.

### 9.2. Test aggregation vs coverage aggregation

| Gradle plugin | Input chính | Output thường gặp |
| --- | --- | --- |
| `test-report-aggregation` | Binary Test results variants | HTML test summary |
| `jacoco-report-aggregation` | JaCoCo execution data + class/source context | Aggregate JaCoCo HTML/XML |
| `jacoco` module | Execution data trên Test tasks | Per-module JaCoCo reports |
| `checkstyle`/`pmd` | Static analysis | Per-module quality reports |

Theo Gradle core plugin documentation, các report aggregators này không phải giải pháp trực tiếp cho `com.android.application`. Android build/test/coverage có toolchain và variants riêng; không sao chép Groovy DSL Java này sang Android mà không xem plugin docs.

## 10. Khi nào chỉ nên tập hợp report folders?

Không phải mọi report đều có common schema để merge:
- Checkstyle HTML của nhiều modules.
- PMD reports với rule sets khác nhau.
- Vulnerability scanners với severity models riêng.
- API docs/sites của từng service.
- Generated architecture reports.

Trong các trường hợp đó, **đặt cạnh nhau theo namespace** thường đúng hơn gộp nội dung:

~~~text
evidence/
├── core/
│   └── checkstyle/index.html
├── app/
│   └── checkstyle/index.html
└── index.html
~~~

File `evidence/index.html` có thể chứa các links tới từng module report. Nó là **portal/index**, không được gọi là “test count/coverage merged result” nếu chưa có data aggregation thực sự.

Để giữ links nội bộ của HTML sites, copy **toàn bộ site tree** vào subdirectory riêng, không chỉ `index.html`. Với các reports có schema JSON/CSV hợp lệ, có thể viết custom merge task nhưng phải khai chính xác inputs, schema validation, duplicate handling và output.

### 10.1. Giữ provenance

Mỗi report artifact nên có:
- Module/project path.
- Report kind/test suite name.
- Version/build ID/commit provenance nếu release policy yêu cầu.
- Tool version và rules version khi cần.
- Result status và số tests/failures thật.
- Thời điểm CI/job metadata **ngoài artifact content** nếu muốn báo cáo tái lập.
- Không lộ secrets từ logs và test data.

Nếu chỉ có một `index.html` bị overwrite, mất thông tin module sở hữu báo cáo, pipeline không đạt mục tiêu.

## 11. Custom artifact variants khi module không có Java JAR

Trong lab, Java plugin đã tạo `runtimeElements`; `:bundle` không cần định nghĩa outgoing variants mới. Nhưng nếu module tạo `api-schema.json`, `analysis.json` hoặc `generated-contract.zip`, Gradle không tự biết đây là artifact nào cần chia sẻ.

Khi đó:
1. Producer task khai `@Input`/`@InputFiles`, `@OutputFile`/`@OutputDirectory`.
2. Module tạo **consumable configuration** cho artifact loại đó, có attributes khác biệt.
3. Đưa task output vào `artifacts` của configuration, có producer dependency.
4. Consumer khai **resolvable configuration** với compatible attributes và project dependency.
5. Consumer task nhận resolved artifact files như inputs và xuất output mới của riêng mình.

### 11.1. Snippet ở producer

Đây là **snippet có điều kiện**, không phải full runnable lab (task `generateApiSchema` cần được định nghĩa trước):

~~~groovy
import org.gradle.api.attributes.Attribute

def schemaOutput = layout.buildDirectory.file('generated/schema/api.json')

configurations {
    apiSchemaElements {
        canBeConsumed = true
        canBeResolved = false
        attributes {
            attribute(
                Attribute.of('dev.demo.artifact.kind', String),
                'api-schema'
            )
        }
    }
}

artifacts {
    add('apiSchemaElements', schemaOutput) {
        builtBy tasks.named('generateApiSchema')
        type = 'json'
    }
}
~~~

Cấu hình này công bố một schema output có **artifact identity** rõ hơn “file đuôi json bất kỳ trong build”. Task generate cần thật sự tạo output `schemaOutput` và khai output property. `builtBy` mô tả task producer.

### 11.2. Consumer phải chọn đúng variant

Consumer cấu hình matching attribute `dev.demo.artifact.kind=api-schema` và khai project dependency tương ứng. Nếu module có nhiều outgoing artifacts nhưng không có attributes phân biệt, Gradle có thể báo **ambiguous variant selection** hoặc lấy sai artifact.

Dùng Gradle diagnostics:

~~~bash
./gradlew :core:outgoingVariants
./gradlew :bundle:resolvableConfigurations
~~~

Đừng chỉ dựa vào tên file/classifier; một contract tốt cần phân biệt **semantic artifact kind**, producer task và data format/version.

## 12. Duplicate file names và ranh giới module

Nếu hai modules cùng tạo `library.jar`, việc copy vào một folder phẳng khiến hai artifacts cạnh tranh cùng destination path.

Trong lab `:bundle` đã đặt:

~~~groovy
duplicatesStrategy = DuplicatesStrategy.FAIL
~~~

để **fail-fast**. Không “chữa” bằng `EXCLUDE`/`INCLUDE` tùy tiện:
- `EXCLUDE` bỏ artifact thứ hai dựa trên thứ tự copy, có thể làm mất module quan trọng.
- `INCLUDE` trong ZIP có thể dẫn tới duplicate entry names, consumer đọc không nhất quán.
- `WARN` cảnh báo nhưng không giải quyết ownership.
- `FAIL` buộc người thiết kế xác định tên/namespace.

**Cách sửa:**
- Đặt archiveBaseName/artifact filename độc nhất theo module.
- Dùng output hierarchy `libs/core/...`, `libs/app/...` khi có hai files cùng tên, với CopySpecs có producer inputs tách biệt.
- Nếu cần “fat JAR”, chọn plugin shading/merging chuyên dụng, kiểm tra `META-INF/services`/licenses/duplicate resources; không coi ZIP chứa nhiều JAR là fat JAR.

## 13. Configuration cache và Isolated Projects

### 13.1. Isolated Projects

Gradle Isolated Projects hạn chế quan sát/mutate mutable state của project khác trong project-scope configuration:
- Không gọi `project(':core').tasks` để lấy TaskProvider cho root.
- Không gọi `project(':app').layout.buildDirectory`.
- Không dùng `subprojects { ... }` để sửa tất cả modules như một cơ chế mặc định.

Lệnh task-path-only `dependsOn ':core:check'` **được phép** cho lifecycle orchestration. Khi thực sự đọc output cross-project, dùng project dependency/outgoing variant.

### 13.2. Configuration cache khác build cache

| Cơ chế | Tái sử dụng gì? | Điều không được khẳng định |
| --- | --- | --- |
| Configuration cache | Task graph/configuration state | Không bảo đảm artifact output đã được tạo |
| Build cache | Cacheable task outputs dựa trên inputs/implementation | Không thay thế đúng logic producer/consumer |
| Up-to-date check | Output có thể không cần tính lại khi inputs hợp lệ | Không phải quality assurance của CI |
| Artifact variants | Contract của outgoing/incoming artifacts | Không tự kiểm tra mọi release policy/security |

Custom aggregator action phụ thuộc thời gian hiện tại, OS user, đường dẫn tuyệt đối hoặc đọc task/project state chưa khai input sẽ khó tái lập và có thể gây configuration-cache errors.

### 13.3. Parallel execution

~~~bash
./gradlew releaseEvidence --parallel
~~~

Với ranh giới output rõ, các modules có thể chạy song song trong điều kiện Gradle task graph cho phép. Nhưng nếu `:core:test` và `:app:test` cùng ghi vào `root/build/reports/test` thì vẫn có race dù tool tự động hóa tốt đến đâu.

**Không dùng shared output directory cho producers.** Aggregator output mới của `:reports` là một dữ liệu khác, không thay thế quyền sở hữu report gốc.

## 14. CI, failed tests và release gating

### 14.1. `--continue` không làm failed tests thành PASS

~~~bash
./gradlew releaseEvidence --continue
~~~

Khi một task `test` fail, Gradle cố chạy tasks khác không bị blocked để thu diagnostics. **Overall build phải vẫn FAIL**; aggregation report có thể không sinh đủ nếu task phụ thuộc producer thất bại.

Trong CI, bạn có thể upload:
- Aggregate HTML dưới `reports/build/reports/**` khi có.
- Raw test results `core/build/test-results/test/**` và `app/build/test-results/test/**`.
- Per-module HTML reports.
- ZIP `bundle/build/archives/module-jars-1.0.0.zip` chỉ được **phát hành** sau khi quality gate PASS.

### 14.2. Artifact tồn tại không đồng nghĩa đã đạt chất lượng

Một ZIP có thể được tạo trước khi test fail trong cùng Gradle graph. Không được coi việc file tồn tại là tín hiệu “release approved”. CI cần kiểm tra exit code và trusted release context.

Một nguyên tắc workflow:
1. Checkout commit/tag.
2. Setup JDK/Gradle Wrapper/caches.
3. Chạy `releaseEvidence` hoặc `verifyModules`/`collectEvidence` theo policy.
4. Lưu reports để debug (kể cả khi failed).
5. Chỉ publish binary artifacts vào repository sản phẩm nếu tests/checks PASS và job có quyền release.
6. Không cấp release credentials cho untrusted Pull Request builds.

### 14.3. Tách CI artifacts theo mục đích

- **Distribution binary:** `bundle/build/archives/module-jars-1.0.0.zip`.
- **Aggregate test report:** output của `:reports:testAggregateTestReport`.
- **Per-module raw results:** `core/build/test-results/test`, `app/build/test-results/test`.
- **Per-module code quality reports:** từng `module/build/reports/checkstyle`/PMD/... khi có.

Giữ module labels và retention/security policy phù hợp. Test logs có thể chứa thông tin môi trường hoặc dữ liệu test, nên không phát tán công khai như bản release binary nếu chính sách không cho phép.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Giải pháp |
| --- | --- | --- |
| `moduleJars` không resolve | Wrong attributes hoặc thiếu Java outgoing variants | Xem `outgoingVariants`/`resolvableConfigurations` |
| `No matching variant` | Usage/Category/LibraryElements/JVM mismatch | Chọn đúng binary runtime variant |
| `Ambiguous variants` | Attributes thiếu | Bổ sung semantic attributes |
| JAR trùng trong distribution | Copy transitive và direct hoặc cùng filename | Direct-only config, unique names, fail-fast |
| Bundle không chạy trên CI | Thiếu external runtime dependencies | Dùng distribution/application plugin hoặc tính đủ runtime classpath |
| Task chỉ chạy sau `jar` nhưng output stale | `dependsOn` không khai file inputs | Dùng outgoing artifact/consuming configuration |
| Root truy cập `project(':core').tasks` bị lỗi | Cross-project mutable access | Dùng task paths cho orchestration, variants cho data |
| HTML report gộp sai | Copy nhiều `index.html` vào chung folder | Test Report Aggregation hoặc folder namespaces |
| Report aggregation rỗng | Không có Test suites/results, project dependency thiếu | Kiểm tra producer tests và `testReportAggregation` |
| `testAggregateTestReport` không tồn tại | Report đăng ký sai hoặc plugin thiếu | Dùng standalone `reporting.reports` DSL |
| Test failed nhưng không có aggregate HTML | Producer failure blocked report task | `--continue` và upload raw reports |
| JaCoCo aggregated report trống | Producers chưa áp JaCoCo/có execution data | Kiểm tra `jacoco` plugins, test execution |
| Aggregate “coverage” sai | Tính trung bình % thay vì data merge | Dùng JaCoCo aggregation tool |
| Config cache fail | Task action capture Project/cross-project mutable state | Managed task inputs/providers/isolated plugin |
| ZIP có file cũ | Raw directory glob thay vì selected outgoing artifact | Variant-aware project dependency |
| CI pass sai khi tests failed | `ignoreFailures`/exit code bị bỏ qua | Fail job/release gate đúng |
| Release ZIP không reproducible | Generator/JDK/source/timestamps thay đổi | Pin toolchain, archive options và verify hashes |
| Module report bị xóa khi chạy aggregator | Shared output hoặc `clean` sai thứ tự | Mỗi module sở hữu outputs; Gradle data edges |

### 15.1. Lệnh điều tra

~~~bash
./gradlew projects
./gradlew :core:tasks --all
./gradlew :app:tasks --all
./gradlew :core:outgoingVariants
./gradlew :app:outgoingVariants
./gradlew :bundle:resolvableConfigurations
./gradlew :bundle:dependencies --configuration moduleJars
./gradlew :core:test --info
./gradlew :app:test --info
./gradlew :reports:testAggregateTestReport --info
./gradlew :bundle:packJars --info
./gradlew releaseEvidence --continue
~~~

`--dry-run` chỉ hiển thị task graph, không chạy tests/aggregation. Không dùng `./gradlew releaseEvidence --dry-run` để chứng minh báo cáo đúng.

## 16. Bài tập và đáp án

### Bài 1 — Task orchestration
**Hỏi:** Root chỉ cần chạy `:core:check` và `:app:check`, không dùng output. Cách gì?

**Đáp án:** `dependsOn ':core:check', ':app:check'` ở lifecycle task. Đây là task ordering theo path.

### Bài 2 — Artifact data dependency
**Hỏi:** Muốn lấy binary Jar của core từ bundle. Có nên dùng `project(':core').tasks.named('jar')`?

**Đáp án:** Không nên vượt module boundary. Dùng project dependencies vào resolvable configuration với attributes phù hợp.

### Bài 3 — Gộp HTML
**Hỏi:** Copy `core/index.html` và `app/index.html` vào cùng folder, liệu có tạo report tổng hợp đúng?

**Đáp án:** Không. Có thể overwrite/duplicate/links hỏng; dùng `test-report-aggregation` hoặc giữ folder riêng.

### Bài 4 — `transitive=false`
**Hỏi:** Vì sao bundle lab chỉ gồm hai JAR?

**Đáp án:** Configuration `moduleJars` lấy hai project dependencies trực tiếp, `transitive=false`. Nếu app cần third-party runtime libs, cách này không tạo complete distribution.

### Bài 5 — Coverage
**Hỏi:** Core 100% coverage, app 20%. Có thể cho coverage tổng 60%?

**Đáp án:** Không, cần execution data/class/source context và tổng mẫu số chính xác, không lấy trung bình đơn giản.

### Bài 6 — Failure
**Hỏi:** `--continue` có cho CI PASS khi `:core:test` FAIL không?

**Đáp án:** Không. Nó chỉ tiếp tục tasks khả thi, overall build vẫn FAIL.

### Bài 7 — ZIP
**Hỏi:** `module-jars-1.0.0.zip` có phải executable fat JAR?

**Đáp án:** Không; ZIP chứa hai JAR. Runtime cần classpath thích hợp hoặc distribution plugin.

### Bài 8 — Outputs
**Hỏi:** Vì sao không để `:core:test` và `:app:test` cùng ghi `root/build/reports/test`?

**Đáp án:** Hai tasks cùng sở hữu một output path gây data races, overwrite và làm incremental/task caching sai.

### Bài 9 — Consumer variant
**Hỏi:** `:bundle` nên chọn `java-api` hay `java-runtime` cho binary distribution?

**Đáp án:** `java-runtime` cùng `library` và `jar` phù hợp để lấy runtime JAR artifacts theo mục tiêu lab.

### Bài 10 — Report owner
**Hỏi:** Project nào sở hữu aggregate HTML output?

**Đáp án:** `:reports`. Raw test reports vẫn do `:core`/`:app` sở hữu.

### Bài 11 — Module version thay đổi
**Hỏi:** Đổi `:core` version/`archiveBaseName`, điều gì xảy ra khi aggregator hard-code filename?

**Đáp án:** Dễ bị stale/missing file. Variant-aware consumer lấy artifact được Gradle công bố theo model mới.

### Bài 12 — Thực hành tự kiểm tra
1. Tạo project bốn modules với đủ files phần 5–7.
2. Chạy `./gradlew :core:test :app:test`, xác nhận hai tests PASS.
3. Chạy `verifyModules`, xem các module vẫn tự tạo test reports.
4. Chạy `:reports:testAggregateTestReport`, xác nhận HTML gồm hai test cases.
5. Chạy `:bundle:collectJars`/`packJars`, kiểm tra có đúng hai binary JARs.
6. Chạy `jar tf` trên ZIP và kiểm tra entries.
7. Chạy `:app:run --quiet` và `java -cp` bằng bundled JARs; đối chiếu stdout.
8. Cố tình làm core unit test fail, chạy `releaseEvidence --continue`; overall build vẫn FAIL.
9. Đổi một module's `archiveBaseName` và xác minh collector dùng variant output mới.
10. Thử Gradle `--parallel` và kiểm tra các output directories độc lập.
11. Giải thích cách thêm JaCoCo report aggregation khi có coverage data.
12. Chỉ ra vì sao root không được đọc mutable state của subprojects.

**Tiêu chí đạt:** giải thích và thực hành được root orchestration, variant-aware artifact flow, test result aggregation, CI failure handling mà không làm mất ranh giới module.

## 17. Checklist áp dụng thực tế

- [ ] `settings.gradle` khai modules rõ và directories tồn tại.
- [ ] Từng module sở hữu source/tests/JAR/reports.
- [ ] Root chỉ điều phối named lifecycle tasks, không truy cập mutable task state của module khác.
- [ ] Artifact aggregation qua project dependencies/outgoing variants, không raw `../module/build` paths.
- [ ] Incoming configuration chỉ rõ resolvable/consumable role và variant attributes.
- [ ] Tránh copy stale artifacts/classifiers không mong đợi.
- [ ] Duplicates strategy FAIL hoặc chính sách namespace rõ.
- [ ] Transitive runtime dependencies được xử lý đúng theo mục tiêu bàn giao.
- [ ] Test report dùng test results variants, không chỉ copy HTML sites.
- [ ] JaCoCo coverage tính trên execution data/class context, không trung bình phần trăm.
- [ ] Root report index giữ module identity khi chỉ tập hợp sites.
- [ ] `:bundle`/`:reports` có output directories riêng, không rewrite module outputs.
- [ ] Generated data có input/output ownership rõ và deterministic.
- [ ] Tests fail dẫn tới CI/release gate fail, dù `--continue` thu reports.
- [ ] Không cấp release permissions cho untrusted PRs.
- [ ] Raw module reports được giữ lại khi aggregate report không tạo được.
- [ ] Gradle Wrapper/JDK/tool/plugin versions được kiểm soát.
- [ ] Có QA cho output ZIP/report paths và artifact provenance.
- [ ] Configuration cache/isolated projects behavior được kiểm tra theo môi trường thật.
- [ ] Multi-project convention plugins thay cross-project configuration injection khi cần chia sẻ logic.

## 18. Tài liệu Gradle chính thức

- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): project layout, module boundaries và project dependencies.
- [Gradle — Structuring Multi-Project Builds](https://docs.gradle.org/current/userguide/intro_multi_project_builds.html): project/task paths và root orchestration.
- [Gradle — How to Share Artifacts Between Projects](https://docs.gradle.org/current/userguide/how_to_share_outputs_between_projects.html): outgoing artifacts, consumable/resolvable configurations, attributes.
- [Gradle — Isolated Projects](https://docs.gradle.org/current/userguide/isolated_projects.html): hạn chế cross-project mutable state, task-path orchestration.
- [Gradle — Test Report Aggregation Plugin](https://docs.gradle.org/current/userguide/test_report_aggregation_plugin.html): `testReportAggregation`, `AggregateTestReport` và test-result variants.
- [Gradle — JaCoCo Report Aggregation Plugin](https://docs.gradle.org/current/userguide/jacoco_report_aggregation_plugin.html): `jacocoAggregation` và coverage report variants.
- [Gradle — JVM Test Suite Plugin](https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html): `test` suite outputs và verification attributes.
- [Gradle — Variant Attributes](https://docs.gradle.org/current/userguide/variant_attributes.html): `Usage`, `Category`, `LibraryElements`.
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html): resolvable/consumable/dependency-scope configurations.
- [Gradle — Working With Files](https://docs.gradle.org/current/userguide/working_with_files.html): `Sync`, `Copy`, `Zip`, duplicates handling.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `tasks.register` và `tasks.named`.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): build logic requirements và cached graph.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): inputs/outputs, task caching và reproducibility.

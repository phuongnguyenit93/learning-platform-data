# Cấu hình heap, JVM args, system properties và test logging trong Gradle

## 1. Bối cảnh: tại sao bài test chạy khác ứng dụng hoặc khác CI?

Một bộ kiểm thử Java có thể chạy ổn trên laptop nhưng thất bại trong CI vì bộ nhớ, Java runtime, JVM arguments, system properties hoặc cách ghi log. Những triệu chứng quen thuộc:

- `java.lang.OutOfMemoryError: Java heap space` khi bộ test tạo nhiều object.
- Một test đọc `System.getProperty("app.profile")` thấy `null` dù developer đã truyền `-Dapp.profile=ci` cho Gradle.
- Test có `System.out.println(...)` nhưng output không hiện ở console.
- Test chạy lại thấy `UP-TO-DATE` nên không có log mới.
- Các test chạy song song gây tranh chấp database/file/port.
- Stacktrace trong CI bị rút gọn, khó xác định nguyên nhân gốc.
- Java process của test bị hệ điều hành kill vì tổng memory vượt giới hạn container, dù `maxHeapSize` tưởng như hợp lý.

Các tình huống trên cần giải quyết ở **task `Test` của Gradle**. Plugin `java` hoặc `java-library` tạo source set `test` và task `test` kiểu `org.gradle.api.tasks.testing.Test`; plugin `application` cũng tích hợp Java support. Test task thực thi tests trong **một hoặc nhiều JVM process riêng** với JVM chạy Gradle daemon.

Bài này thuộc chủ đề cha **Kiểm thử** của module **Build Tool Gradle**. Trọng tâm là bốn nhóm cài đặt:

1. **Heap:** `minHeapSize`, `maxHeapSize` và tổng ngân sách bộ nhớ.
2. **JVM args:** `jvmArgs(...)` và các JVM flags của **test worker process**.
3. **System properties:** `systemProperty(...)`/`systemProperties(...)` và sự khác biệt giữa `-P` với `-D`.
4. **Test logging:** `testLogging`, `events(...)`, `showStandardStreams`, `exceptionFormat` và test reports.

Sau bài học, bạn có thể cấu hình một project Java 17 + JUnit Jupiter chạy được, kiểm tra stdout, tái hiện lỗi property/logging và chọn cấu hình CI phù hợp mà không che lỗi thực sự.

## 2. Trước tiên, phân biệt ba tầng JVM

Một build Java có thể liên quan nhiều tiến trình:

~~~text
Terminal hoặc IDE
       |
       v
Gradle client / Gradle daemon JVM
       |  cấu hình bằng Gradle runtime/JVM settings
       |
       +--------------------> JavaCompile task
       |                      JDK compiler/toolchain (javac)
       |
       +--------------------> Test task
                                 |
                                 +--> Test worker JVM #1
                                 |     -Xms, -Xmx
                                 |     jvmArgs(...)
                                 |     -Dsystem.properties
                                 |     JUnit Platform / JUnit Jupiter
                                 |
                                 +--> Test worker JVM #2 (nếu cho song song)
                                       cùng cấu hình task nhưng process riêng
~~~

**Mấu chốt:** `org.gradle.jvmargs=-Xmx2g` trong `gradle.properties` chủ yếu cấu hình **JVM chạy Gradle daemon**, không phải tự động cấp heap 2 GiB cho các test worker JVM.

Ngược lại, cấu hình:

~~~kotlin
tasks.withType<Test>().configureEach {
    maxHeapSize = "512m"
}
~~~

đặt giới hạn heap cho **mỗi JVM test worker** mà task tạo ra, không thay giới hạn heap của Gradle daemon và không tự đổi heap của ứng dụng chạy production.

### 2.1. Bảng phân biệt nhanh

| Điều muốn cấu hình | API/nơi phù hợp | Không nên nhầm với |
| --- | --- | --- |
| Heap của Gradle daemon | `org.gradle.jvmargs`, daemon JVM options | Heap của test worker |
| Heap của test JVM | `Test.minHeapSize`, `Test.maxHeapSize` | `JavaCompile` heap hoặc Gradle daemon |
| JVM flags của test worker | `Test.jvmArgs(...)` | `gradle --info`, `gradle --stacktrace` |
| Properties mà test đọc qua `System.getProperty` | `Test.systemProperty(...)` | Gradle `-P` nếu chưa forward |
| Toolchain/JDK chạy tests | `Test.javaLauncher`, Java toolchain | `System.getProperty("java.version")` của daemon |
| Log các test cases | `Test.testLogging` | Gradle build logging chung |
| Test result files | `Test.reports`, `build/test-results` | Chỉ những dòng console |
| Parallel test processes | `Test.maxParallelForks` | Gradle `--parallel` ở cấp projects |

Nếu muốn điều tra lỗi memory, log và version, cần xác định **process nào thật sự thất bại** trước khi chỉnh.

## 3. Cấu hình heap: minHeapSize và maxHeapSize

### 3.1. Heap là gì?

Java heap là vùng nhớ để JVM cấp phát phần lớn Java objects. Hai flags thông dụng:

- `-Xms`: kích thước heap **ban đầu**.
- `-Xmx`: giới hạn heap **tối đa**.

Gradle Test API cung cấp hai properties tương ứng:

~~~kotlin
tasks.named<Test>("test") {
    minHeapSize = "128m"
    maxHeapSize = "512m"
}
~~~

Tương đương về ý định:

~~~text
Test worker JVM: -Xms128m -Xmx512m
~~~

Cú pháp `"128m"`, `"512m"` là chuỗi kích thước được JVM/Gradle chấp nhận. Chọn con số dựa trên nhu cầu thật và giới hạn máy/container, không có “một con số đúng” cho mọi test suite.

### 3.2. Kotlin DSL vs Groovy DSL

Kotlin DSL (`build.gradle.kts`):

~~~kotlin
tasks.withType<Test>().configureEach {
    minHeapSize = "128m"
    maxHeapSize = "512m"
}
~~~

Groovy DSL (`build.gradle`):

~~~groovy
tasks.withType(Test).configureEach {
    minHeapSize = '128m'
    maxHeapSize = '512m'
}
~~~

`tasks.withType<Test>().configureEach` áp dụng cho **mọi Test task** trong **project hiện tại**, kể cả test tasks được đăng ký sau đó. `tasks.named<Test>("test")` chỉ cấu hình task có tên `test`. Nếu một project có `integrationTest`, `functionalTest`... có thể muốn cài đặt chung hoặc riêng tùy nhu cầu.

### 3.3. minHeapSize không có nghĩa “JVM chỉ được dùng 128 MiB”

`minHeapSize` tác động kích thước heap ban đầu; `maxHeapSize` đặt tối đa heap. JVM có thể dùng bộ nhớ **ngoài heap**:

- Metaspace chứa metadata của classes.
- Thread stacks.
- JIT/code cache.
- Native/direct buffers.
- JVM native allocations.
- Memory của process và native libraries.
- Dữ liệu I/O được OS page cache giữ, không phải tất cả thuộc RSS của test JVM.

Vì vậy test process có `-Xmx512m` **không có nghĩa tổng RSS ≤512 MiB**. Khi bị Linux OOM-killer/container kill, tăng `-Xmx` có thể làm tình trạng tệ hơn.

### 3.4. Không trộn flags heap trùng nhau

Mẫu nên tránh:

~~~kotlin
tasks.named<Test>("test") {
    maxHeapSize = "512m"
    jvmArgs("-Xmx2g") // Hai nơi cùng cấu hình Xmx, gây khó hiểu.
}
~~~

Dù launcher có cơ chế xây command line, **không nên dựa vào thứ tự flags** để đoán cái nào thắng. Hãy chọn một cách chính: `maxHeapSize`/`minHeapSize` cho heap; dành `jvmArgs(...)` cho những JVM flags khác.

### 3.5. Giới hạn ngân sách bộ nhớ khi có nhiều worker

Ví dụ:

~~~kotlin
tasks.named<Test>("test") {
    maxHeapSize = "512m"
    maxParallelForks = 4
}
~~~

Nếu cả 4 test workers chạy đồng thời, **chỉ riêng các upper bounds của heap** đã là khoảng 4 × 512 MiB = 2 GiB; cộng Gradle daemon, compiler, Metaspace, native memory, OS/process overhead còn lớn hơn.

Với CI container 2 GiB, cấu hình trên rất dễ bị OOM-killer, nhất là khi còn tasks khác chạy song song. Giải pháp có thể là:

- Hạ `maxParallelForks` xuống 1 hoặc 2.
- Tăng memory limit của runner khi có cơ sở.
- Giảm memory use của test fixture, chia test suite hoặc dọn resources.
- Thu hẹp task concurrency ở project level.
- Giám sát memory thật và chỉ tăng heap khi lỗi thực sự là `Java heap space`.

**Không lấy số core CPU để tự suy ra số parallel workers an toàn về memory.**

## 4. JVM args: jvmArgs(...) có tác dụng gì?

`jvmArgs(...)` truyền những **JVM options** bổ sung khi Gradle khởi chạy **test worker JVM**.

Ví dụ:

~~~kotlin
tasks.named<Test>("test") {
    jvmArgs("-ea")
    jvmArgs("-Ddemo.jvm.flag=enabled")
}
~~~

- `-ea` bật Java assertions trong JVM (Gradle thường bật assertions cho tests; ví dụ này làm ý định rõ).
- `-Ddemo.jvm.flag=enabled` thiết lập một JVM system property.
- Những flags `-XX:...` có thể điều khiển GC, heap dump, JIT, v.v. nhưng phụ thuộc Java version và môi trường.

### 4.1. Một cách cấu hình cụ thể, dễ review

~~~kotlin
tasks.named<Test>("test") {
    minHeapSize = "128m"
    maxHeapSize = "512m"

    jvmArgs(
        "-ea",
        "-Ddemo.jvm.flag=enabled"
    )
}
~~~

Nếu chỉ muốn truyền system property, `systemProperty("demo.jvm.flag", "enabled")` thường diễn đạt ý định **rõ hơn** là một chuỗi `-D` trong `jvmArgs`.

### 4.2. jvmArgs không phải program args

Lệnh Java:

~~~bash
java -Xmx512m -Ddemo.jvm.flag=enabled -cp out demo.HeapProbe one two
~~~

Trong đó:

- `-Xmx512m` và `-Ddemo.jvm.flag=enabled` là **JVM options**, nằm **trước** main class.
- `one two` là **program arguments** mà phương thức `main(String[] args)` đọc.
- Test task khởi chạy framework tests, không phải ứng dụng Java tùy ý; muốn cấp tham số cho test thường qua framework config, system properties hoặc fixture thay vì giả định `jvmArgs` sẽ trở thành `String[] args` của application.

Trong Gradle, `JavaExec`/`application:run` có API `args(...)` cho program arguments; `Test` không phải task `JavaExec` và có mô hình test launcher riêng.

### 4.3. Ví dụ flags chẩn đoán memory

~~~kotlin
tasks.named<Test>("test") {
    jvmArgs(
        "-XX:+HeapDumpOnOutOfMemoryError"
    )
}
~~~

Flag HotSpot này yêu cầu ghi heap dump khi có lỗi OOM phù hợp. **Lưu ý:** Heap dump có thể rất lớn và chứa dữ liệu nhạy cảm từ test fixtures/credentials. Trong CI cần chọn đường lưu riêng, quyền truy cập, retention và không công bố dump tự động.

Nếu cần chỉ định path:

~~~kotlin
tasks.named<Test>("test") {
    jvmArgs(
        "-XX:+HeapDumpOnOutOfMemoryError",
        "-XX:HeapDumpPath=build/heapdumps"
    )
}
~~~

Đây là cấu hình minh họa; phải bảo đảm thư mục output tồn tại và có quyền ghi. Với nhiều workers chạy song song, hãy tránh để nhiều processes cố ghi trùng một tên file; quản lý artifacts và đường dẫn theo worker hoặc điều kiện CI.

### 4.4. --add-opens và Java 17+

Một số libraries cũ truy cập nội bộ JDK bằng reflection, dẫn tới `InaccessibleObjectException`. Có thể thấy workaround như:

~~~kotlin
tasks.named<Test>("test") {
    jvmArgs(
        "--add-opens=java.base/java.lang=ALL-UNNAMED"
    )
}
~~~

Đây **không phải** cấu hình mặc định nên áp dụng mọi nơi. Nó mở quyền reflection ở một package cụ thể, có tác động encapsulation. Chỉ thêm khi stacktrace chứng minh nhu cầu, ưu tiên nâng dependency/plugin để dùng public APIs và giữ phạm vi tại test worker cần thiết.

### 4.5. Cảnh báo với JVM flags lỗi thời

Không copy một flag `-XX` từ blog cũ nếu chưa kiểm tra JDK. Chẳng hạn `-XX:MaxPermSize` đã lỗi thời/không còn hợp lệ trên JVM hiện đại. Java 17 khác Java 8 ở GC defaults, metadata và module access. Một `Unrecognized VM option` khiến test worker **không khởi động được**, dù Java source/test code hoàn toàn đúng.

## 5. systemProperty và systemProperties

Một system property là cặp **key-value trong JVM process**, có thể đọc bằng:

~~~java
String value = System.getProperty("demo.test.profile");
~~~

Trong Gradle Kotlin DSL:

~~~kotlin
tasks.named<Test>("test") {
    systemProperty("demo.test.profile", "ci")
}
~~~

Hoặc nhiều giá trị:

~~~kotlin
tasks.named<Test>("test") {
    systemProperties(
        mapOf(
            "demo.test.profile" to "ci",
            "feature.alpha" to "on"
        )
    )
}
~~~

Groovy DSL:

~~~groovy
tasks.named('test', Test) {
    systemProperty 'demo.test.profile', 'ci'
    systemProperties([
        'feature.alpha': 'on',
        'feature.beta': 'off'
    ])
}
~~~

Đặt property trên task `Test` giúp Gradle truyền nó cho **forked test JVM**. Đây là cách đọc được bằng `System.getProperty(...)` trong JUnit test.

### 5.1. Phân biệt -P và -D

Hai CLI options nhìn giống nhưng khác namespace:

~~~bash
./gradlew test -PtestProfile=ci
./gradlew test -Ddemo.test.profile=ci
~~~

- `-PtestProfile=ci` thiết lập **Gradle project property**: truy cập bằng `providers.gradleProperty("testProfile")`.
- `-Ddemo.test.profile=ci` thiết lập **system property của Gradle process**, truy cập bằng `providers.systemProperty("demo.test.profile")` ở Gradle build logic.
- **Không mặc định** suy ra rằng `-D...` trên command line sẽ tự forward thành system property của test worker JVM.
- Cách chắc chắn: map giá trị mong muốn từ Gradle configuration sang `Test.systemProperty(...)`.

Ví dụ Kotlin DSL:

~~~kotlin
val testProfile = providers.gradleProperty("testProfile")
    .orElse("local")

tasks.named<Test>("test") {
    systemProperty("demo.test.profile", testProfile.get())
}
~~~

CLI:

~~~bash
./gradlew test -PtestProfile=ci
~~~

Test đọc:

~~~java
System.getProperty("demo.test.profile") // "ci"
~~~

Đoạn comment trên thể hiện **giá trị dự kiến**, không phải một program hoàn chỉnh. `Provider.get()` trong cấu hình task được Gradle theo dõi như configuration input khi dùng API phù hợp; với nhiều custom tasks hoặc nhu cầu Configuration Cache nâng cao, nên xem cách wiring providers và inputs của task riêng.

### 5.2. Nếu team muốn dùng -D trên CLI

Có thể chủ động forward:

~~~kotlin
val profileFromGradleSystemProperty =
    providers.systemProperty("demo.test.profile").orElse("local")

tasks.named<Test>("test") {
    systemProperty(
        "demo.test.profile",
        profileFromGradleSystemProperty.get()
    )
}
~~~

Khi chạy:

~~~bash
./gradlew test -Ddemo.test.profile=ci
~~~

JUnit test worker nhận `demo.test.profile=ci`. Không viết đồng thời hai cơ chế forward `-P` và `-D` cho cùng key rồi đoán thứ tự ưu tiên; nếu cần hỗ trợ cả hai, định nghĩa **precedence policy** rõ ràng trong build logic.

### 5.3. Environment variable không phải system property

~~~kotlin
val apiMode = providers.environmentVariable("TEST_MODE")
    .orElse("local")

tasks.named<Test>("test") {
    systemProperty("demo.test.profile", apiMode.get())
}
~~~

`TEST_MODE` là biến môi trường; `demo.test.profile` là Java system property. Gradle thực hiện **mapping có chủ đích**. Ứng dụng/test có thể đọc env trực tiếp bằng `System.getenv("TEST_MODE")`, nhưng khi muốn test đáng tái lập và không phụ thuộc máy, tốt hơn là đưa cấu hình rõ thành task inputs/properties.

Không ghi secrets từ environment vào test logs hoặc JUnit XML. Có thể khiến CI công khai password/token dù log đã được filter ở một số nơi.

### 5.4. System property có thể ảnh hưởng JVM trước khi code chạy

Ví dụ `user.timezone` hoặc `java.io.tmpdir` có thể được JVM/framework xử lý sớm. Nếu mục tiêu là cấu hình lúc startup, set bằng `Test.systemProperty(...)` để nó có mặt khi JVM test worker được khởi động. Không tự giả định rằng gọi `System.setProperty(...)` ở giữa test có tác dụng như một JVM startup flag cho mọi component.

### 5.5. Tránh test thay đổi shared system properties không hoàn nguyên

Nếu một test làm:

~~~java
System.setProperty("demo.test.profile", "override");
~~~

test khác trong cùng **worker JVM** có thể quan sát trạng thái đó, gây flaky tests hoặc phụ thuộc thứ tự chạy. Nếu cần thay đổi:

- Lưu giá trị cũ, khôi phục trong `@AfterEach`/`finally`.
- Hạn chế test chạy song song trong cùng JVM khi đụng state toàn cục.
- Ưu tiên dependency injection của configuration vào class đang test.
- Tách test fork khi không thể tránh shared global state.

`systemProperty` của Gradle được đặt ở thời điểm khởi động test worker, không tự reset sau từng test method.

## 6. testLogging: xem đúng mức chi tiết

Gradle có nhiều cấp log: `QUIET`, `WARNING`, `LIFECYCLE`, `INFO`, `DEBUG`. `Test.testLogging` điều khiển **test events** được in ở console; nó khác **Gradle build log level** tổng thể.

Kotlin DSL:

~~~kotlin
import org.gradle.api.tasks.testing.logging.TestExceptionFormat

tasks.named<Test>("test") {
    testLogging {
        events("passed", "skipped", "failed")
        showStandardStreams = true
        exceptionFormat = TestExceptionFormat.FULL
        showExceptions = true
        showCauses = true
        showStackTraces = true
    }
}
~~~

Tác dụng:

- `passed`: có thể hiện test methods đã pass.
- `skipped`: in event tests bị skipped/disabled.
- `failed`: in test failures.
- `showStandardStreams = true`: hiển thị stdout và stderr từ test JVM theo cơ chế test logging.
- `exceptionFormat = FULL`: in stacktrace đầy đủ hơn kiểu `SHORT` khi exception được log.
- `showExceptions/showCauses/showStackTraces`: điều khiển thành phần exception được hiển thị.

### 6.1. TestLogEvent có những sự kiện gì?

Các event phổ biến:

| Event | Khi nào? |
| --- | --- |
| `STARTED` | Một test/suite bắt đầu |
| `PASSED` | Test hoàn thành thành công |
| `FAILED` | Test thất bại |
| `SKIPPED` | Test bị skip |
| `STANDARD_OUT` | Test ghi vào `System.out` |
| `STANDARD_ERROR` | Test ghi vào `System.err` |

Có thể dùng enum thay cho strings:

~~~kotlin
import org.gradle.api.tasks.testing.logging.TestLogEvent

tasks.named<Test>("test") {
    testLogging {
        events(
            TestLogEvent.PASSED,
            TestLogEvent.SKIPPED,
            TestLogEvent.FAILED
        )
        showStandardStreams = true
    }
}
~~~

Dùng enum giúp IDE có autocomplete. Ở mức đơn giản, `events("passed", "skipped", "failed")` là cú pháp được Gradle hỗ trợ.

### 6.2. showStandardStreams khác events("passed")

Một test có:

~~~java
System.out.println("READY");
System.err.println("DIAGNOSTIC");
~~~

không tự buộc Gradle phải in hai dòng ấy ở console theo mọi log level. Khi `showStandardStreams=true`, Gradle có thể đưa output từ stdout/stderr của test worker vào event logging với heading theo test class/method.

**Không nhầm** output của test JVM với `println(...)` trong Gradle build script. Hai dòng xuất hiện ở hai nguồn khác nhau và bị áp dụng logging filters khác nhau.

### 6.3. ExceptionFormat và stacktrace

Có hai dạng cơ bản:

- `TestExceptionFormat.SHORT`: output rút gọn, phù hợp khi CI log nhiều.
- `TestExceptionFormat.FULL`: stacktrace nhiều thông tin hơn để debug.

Ví dụ đổi sang ngắn:

~~~kotlin
import org.gradle.api.tasks.testing.logging.TestExceptionFormat

tasks.named<Test>("test") {
    testLogging {
        events("failed")
        exceptionFormat = TestExceptionFormat.SHORT
    }
}
~~~

Nếu đang điều tra một exception có nested causes, dùng FULL và `showCauses=true`. Nếu cần xem stacktrace của **lỗi Gradle build** (không phải test assertion failure), thêm `--stacktrace` ở CLI là công cụ riêng; hai setting không thay thế nhau.

### 6.4. Mặc định phụ thuộc log level

Theo tài liệu Gradle, test events mặc định khác nhau theo cấp log:

| Gradle log level | Các test events thường được ghi mặc định |
| --- | --- |
| `QUIET`/`WARNING`/`ERROR` | Không in test events thường lệ |
| `LIFECYCLE` | Test failures, stacktrace thường ở dạng ngắn |
| `INFO` | Failures, skipped và standard output/error |
| `DEBUG` | Thông tin events chi tiết hơn, stacktraces đầy đủ |

`testLogging` có thể thay đổi hành vi mặc định, nhưng **Gradle log level vẫn là bộ lọc chung**. Đừng chạy `-q` rồi kết luận `showStandardStreams` “không hoạt động” chỉ vì không có những dòng ở lifecycle level.

### 6.5. --info, --debug và --stacktrace khác nhau

~~~bash
./gradlew test --info
./gradlew test --debug
./gradlew test --stacktrace
~~~

- `--info`: tăng độ chi tiết chung của build và test logging theo INFO configuration.
- `--debug`: rất nhiều output (dễ chứa thông tin nhạy cảm), không nên để bật mặc định CI.
- `--stacktrace`: thêm stacktrace cho Gradle build failures; không phải là cấu hình riêng cho mỗi JUnit assertion.
- `testLogging { exceptionFormat = FULL }`: định dạng exception **trong test event log**.

Nếu mục tiêu chỉ là xem `System.out` của một test cụ thể, tốt hơn là cấu hình `showStandardStreams=true` và lọc test thay vì bật global `--debug`.

### 6.6. Giảm “ngập log” trong CI

Một team có hàng chục nghìn test methods có thể không muốn log mọi `PASSED`, nhất là khi tests chạy parallel. Cấu hình CI có thể chỉ log failures:

~~~kotlin
tasks.named<Test>("test") {
    testLogging {
        events("failed", "skipped")
        showStandardStreams = false
        exceptionFormat = TestExceptionFormat.FULL
    }
}
~~~

Vẫn giữ **JUnit XML/HTML reports** để truy vết pass counts và exceptions. Đừng tắt logs bằng cách bỏ tests hoặc làm test task báo `SUCCESS` khi vẫn có failures.

## 7. Một project Java 17 + JUnit Jupiter chạy được

Project thực hành sẽ chứng minh bốn chủ đề cùng lúc:

- `Test.minHeapSize` và `Test.maxHeapSize` đặt memory cho forked JVM.
- `jvmArgs("-Ddemo.jvm.flag=enabled")` đặt JVM flag minh họa.
- `systemProperty("demo.test.profile", ...)` truyền Gradle `-PtestProfile` cho tests.
- `testLogging.events(...)` và `showStandardStreams` làm các dòng stdout/stderr của một test xuất hiện trong log.

Phiên bản JUnit được pin để bài học có tính tái lập. Cần JDK 17, một bản Gradle tương thích, và mạng hoặc cache Maven Central ở lần resolve dependencies đầu.

### 7.1. Cây thư mục

~~~text
gradle-test-config-lab/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    ├── main/
    │   └── java/
    │       └── demo/
    │           ├── Calculator.java
    │           └── HeapProbe.java
    └── test/
        └── java/
            └── demo/
                └── CalculatorTest.java
~~~

Không bắt buộc root project có application entry point. Plugin `java` tạo sẵn `test` task. `HeapProbe` là class Java chạy độc lập bằng `javac`/`java` để bạn tự thấy tác động của JVM options.

### 7.2. settings.gradle.kts

~~~kotlin
rootProject.name = "gradle-test-config-lab"
~~~

### 7.3. build.gradle.kts hoàn chỉnh

~~~kotlin
import org.gradle.api.tasks.testing.Test
import org.gradle.api.tasks.testing.logging.TestExceptionFormat
import org.gradle.api.tasks.testing.logging.TestLogEvent

plugins {
    id("java")
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    // BOM điều phối version của các JUnit 5 modules.
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

val testProfile = providers.gradleProperty("testProfile")
    .orElse("local")

tasks.named<Test>("test") {
    useJUnitPlatform()

    // Heap của MỖI test worker JVM, không phải Gradle daemon.
    minHeapSize = "128m"
    maxHeapSize = "512m"

    // Dùng -D trong jvmArgs để minh họa cơ chế JVM options.
    jvmArgs("-Ddemo.jvm.flag=enabled")

    // Từ Gradle project property sang test worker system property.
    systemProperty("demo.test.profile", testProfile.get())

    testLogging {
        events(
            TestLogEvent.PASSED,
            TestLogEvent.SKIPPED,
            TestLogEvent.FAILED
        )
        showStandardStreams = true
        exceptionFormat = TestExceptionFormat.FULL
        showExceptions = true
        showCauses = true
        showStackTraces = true
    }
}
~~~

Đây là **toàn bộ build script**, không phải một snippet cần thêm plugin bên ngoài. Giải thích:

1. `id("java")` tạo compile/test tasks và test source set.
2. `mavenCentral()` giúp tải JUnit artifacts; project dùng Java 17 toolchain.
3. JUnit BOM `5.11.4` align các JUnit Jupiter/Platform modules; `testRuntimeOnly("junit-platform-launcher")` làm launcher explicit.
4. `useJUnitPlatform()` cho Gradle chạy JUnit Jupiter tests qua JUnit Platform.
5. `minHeapSize`/`maxHeapSize` áp dụng cho forked test JVMs.
6. `jvmArgs("-Ddemo.jvm.flag=enabled")` tạo property trong test worker; trong production nên ưu tiên `systemProperty` khi mục đích chỉ là một `-D` property.
7. `testProfile` lấy giá trị từ `-PtestProfile` hoặc fallback `local`.
8. `testLogging` ghi pass/fail/skip và test standard streams; exception trace đầy đủ khi test fail.
9. Không dùng `org.gradle.jvmargs` để cấu hình test heap; đây là hai process khác nhau.
10. Không cần tạo `tasks.register("test")` vì Java plugin đã tạo task `test`.

**Phiên bản phụ thuộc:** Ví dụ pin JUnit 5.11.4 để dễ học; với dự án thực tế, chọn BOM/launcher được project kiểm chứng và cập nhật theo chính sách riêng. Java 17 đáp ứng baseline của bộ ví dụ này.

### 7.4. Calculator.java

Tạo `src/main/java/demo/Calculator.java`:

~~~java
package demo;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int a, int b) {
        return a + b;
    }
}
~~~

Đây là class Java 17 hợp lệ, không có dependency ngoài.

### 7.5. HeapProbe.java

Tạo `src/main/java/demo/HeapProbe.java`:

~~~java
package demo;

public final class HeapProbe {
    private HeapProbe() {
    }

    public static void main(String[] args) {
        System.out.println(
                "mode=" + System.getProperty("demo.test.profile", "missing"));
        System.out.println(
                "flag=" + System.getProperty("demo.jvm.flag", "missing"));
        System.out.println(
                "assertions=" + HeapProbe.class.desiredAssertionStatus());
    }
}
~~~

Class này dùng để minh họa rằng JVM flags và properties được nạp **trước khi main chạy**, và `-ea` ảnh hưởng assertion status. Nó không tham gia JUnit tests trừ khi bạn chủ đích gọi nó.

### 7.6. CalculatorTest.java

Tạo `src/test/java/demo/CalculatorTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;

public final class CalculatorTest {

    @Test
    void additionWorks() {
        assertEquals(7, Calculator.add(3, 4));
    }

    @Test
    void propertyAndJvmArgReachTestWorker() {
        String profile = System.getProperty("demo.test.profile");
        String flag = System.getProperty("demo.jvm.flag");

        assertNotNull(profile);
        assertFalse(profile.isBlank());
        assertEquals("enabled", flag);

        System.out.println("TEST_PROFILE=" + profile);
        System.err.println("JVM_FLAG=" + flag);
    }
}
~~~

Hai test methods đúng cú pháp **JUnit Jupiter 5** và dùng Java 17. Không cần `public` cho các test methods Jupiter; JUnit Platform nhận diện `@Test`.

### 7.7. Chạy lần đầu với profile mặc định

Từ root `gradle-test-config-lab`:

~~~bash
gradle clean test
~~~

Nếu project đã có Wrapper, thay `gradle` bằng `./gradlew` (macOS/Linux) hoặc `gradlew.bat` (Windows). Trong project tạo mới **chưa có Wrapper**, `./gradlew` không tự tồn tại; cần một bản Gradle tương thích đã cài để tạo Wrapper khi cần.

**Expected behavior:**

- Gradle compile `Calculator.java`/`HeapProbe.java`.
- Gradle compile `CalculatorTest.java` với JUnit Jupiter dependency.
- `Test` tạo JVM riêng với heap giới hạn, JVM flag và system property.
- Hai tests **pass**.
- Console có thể hiện headings/tên test method theo Gradle version, `PASSED` events và các dòng stdout/stderr.

Trong log, hãy tìm **hai dòng do test method phát ra**:

~~~text
TEST_PROFILE=local
JVM_FLAG=enabled
~~~

Hai dòng trên là **payload thật của test stdout/stderr**, không phải cam kết toàn bộ Gradle console output hoặc thứ tự của các test methods. `JVM_FLAG` được ghi qua `System.err`, Gradle có thể bao nó trong event `STANDARD_ERROR`.

### 7.8. Thay profile bằng Gradle -P

~~~bash
gradle test --rerun-tasks -PtestProfile=ci
~~~

Test method sẽ ghi:

~~~text
TEST_PROFILE=ci
JVM_FLAG=enabled
~~~

Ý nghĩa:

- `-PtestProfile=ci` là project property được build script đọc.
- `systemProperty("demo.test.profile", testProfile.get())` forward vào worker.
- `jvmArgs("-Ddemo.jvm.flag=enabled")` vẫn tạo property `demo.jvm.flag`.
- `--rerun-tasks` giúp test chạy lại dù trước đó Gradle có thể đánh dấu `UP-TO-DATE`.

**Không nhầm:** Test log có thể in thêm `BUILD SUCCESSFUL`, số tests, task messages và timing; những dòng đó không có một stdout cố định trong bài.

### 7.9. Chỉ chạy một test method

~~~bash
gradle test --tests "demo.CalculatorTest.propertyAndJvmArgReachTestWorker" --rerun-tasks
~~~

Gradle lọc test method được chỉ định. Nếu giữ profile mặc định, log payload vẫn là:

~~~text
TEST_PROFILE=local
JVM_FLAG=enabled
~~~

Nếu `--tests` báo “No tests found”, hãy kiểm tra fully qualified class/method, `useJUnitPlatform()`, test runtime engine và source path. Không dùng test filtering để che những tests khác đang fail trong CI.

### 7.10. Xem test reports dù console đã bị rút gọn

Sau `gradle test`, Java plugin thường tạo:

~~~text
build/reports/tests/test/index.html
build/test-results/test/TEST-demo.CalculatorTest.xml
~~~

- **HTML:** mở `build/reports/tests/test/index.html` để xem suites, tests, outcomes, failures và output theo thiết kế report.
- **JUnit XML:** phù hợp với CI reporters và test result parsers.
- **Console logging:** giúp xem nhanh trong terminal, nhưng không thay thế files báo cáo.

Các đường dẫn áp dụng cho task mặc định `test` của Java plugin, khi reports được bật và không đổi output location. Custom Test tasks có tên/report location tương ứng.

## 8. Kiểm chứng riêng JVM flags bằng javac/java (không cần JUnit)

Để tách bạch vấn đề Gradle/JUnit khỏi JVM, bạn có thể compile Java class `HeapProbe` độc lập.

### 8.1. macOS/Linux

~~~bash
mkdir -p out
javac -d out src/main/java/demo/HeapProbe.java
java -Xms128m -Xmx512m -ea \
  -Ddemo.test.profile=ci \
  -Ddemo.jvm.flag=enabled \
  -cp out demo.HeapProbe
~~~

**Stdout chính xác của Java program:**

~~~text
mode=ci
flag=enabled
assertions=true
~~~

Dòng `assertions=true` do `-ea` bật assertions cho class; dòng mode và flag từ `-D`. Chương trình **không in giới hạn heap chính xác** vì giới hạn mà JVM báo có thể được điều chỉnh/round theo GC và flags.

### 8.2. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -d out src\main\java\demo\HeapProbe.java
java -Xms128m -Xmx512m -ea -Ddemo.test.profile=ci -Ddemo.jvm.flag=enabled -cp out demo.HeapProbe
~~~

Stdout giống mục 8.1. Lệnh PowerShell trên chỉ dùng JVM flags không có khoảng trắng; với các giá trị có dấu cách, dùng cách quote phù hợp với shell.

### 8.3. Không truyền JVM args sau class name

Sai:

~~~bash
java -cp out demo.HeapProbe -Ddemo.jvm.flag=enabled
~~~

Phần `-Ddemo.jvm.flag=enabled` **sau** class name là **program argument** trong `String[] args`, không phải VM option. `HeapProbe` không đọc `args`, nên sẽ in `flag=missing` nếu không có nguồn khác đặt property đó.

Đúng:

~~~bash
java -Ddemo.jvm.flag=enabled -cp out demo.HeapProbe
~~~

Phép thử này giúp tách lỗi lệnh Java khỏi lỗi Gradle Test API. Nó không tự kiểm chứng Gradle launcher tạo đúng flags; để kiểm chứng Gradle hãy chạy bài JUnit ở mục 7.

## 9. Gradle daemon JVM khác test worker JVM

Có ba kiểu cấu hình thường bị trộn:

### 9.1. gradle.properties: org.gradle.jvmargs

~~~properties
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
~~~

Lệnh này nhắm tới **Gradle JVM/daemon**, hữu ích khi chính Gradle configuration/task graph/annotation processing gặp áp lực bộ nhớ. Nó **không** tự set `-Xmx2g` cho test worker.

Đừng đặt password/token trực tiếp trong gradle.properties được commit. Và lưu ý `file.encoding` không thể thay thế việc code chủ động dùng UTF-8 khi serializing data.

### 9.2. build.gradle.kts: Test.maxHeapSize

~~~kotlin
tasks.named<Test>("test") {
    maxHeapSize = "768m"
}
~~~

Chỉ task `test`, mỗi forked worker JVM. Nếu CI có nhiều worker hoặc nhiều Gradle projects cùng test, tổng memory có thể cao hơn rất nhiều 768 MiB.

### 9.3. java.toolchain: JDK dùng bởi test launcher

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Chọn Java toolchain cho các JVM tasks được hỗ trợ. Nếu bạn muốn chỉ định rõ Test launcher:

~~~kotlin
tasks.named<Test>("test") {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(17))
    })
}
~~~

Khi tests được compile target Java 21 nhưng chạy bằng Java 17, JVM test worker có thể gặp `UnsupportedClassVersionError`. Tăng heap **không chữa được** bytecode mismatch; cần kiểm tra Java compiler target và runtime.

## 10. Parallel forks, forkEvery và bộ nhớ

### 10.1. maxParallelForks

~~~kotlin
tasks.named<Test>("test") {
    maxParallelForks = 2
    maxHeapSize = "512m"
}
~~~

Có thể có tối đa hai test worker processes song song **trong task này**, tùy số tests, Gradle worker resources và build scheduling. Tăng `maxParallelForks` không bảo đảm giảm runtime vì tests có thể tranh CPU, disk, ports, database hoặc memory.

### 10.2. forkEvery

~~~kotlin
tasks.named<Test>("test") {
    forkEvery = 25
}
~~~

Thiết lập này yêu cầu một test process được tái tạo sau một số lượng **test classes** đã xử lý (cơ chế Gradle tính theo class), giúp giới hạn tích lũy trạng thái trong worker lâu sống. Giá trị `0` là mặc định, nghĩa không buộc fork theo ngưỡng class.

**Đừng nhầm** `forkEvery = 1` với “mỗi @Test method là một JVM”. Nó gần với việc fork sau mỗi **test class**, nên rất tốn thời gian startup và có thể làm test suite chậm.

### 10.3. Trường hợp test rò rỉ state

Nếu các tests thay `System.setProperty`, static caches, thread-local hoặc global singleton không hoàn nguyên, chạy nhiều test classes trong một JVM có thể gây flaky results. Cách sửa ưu tiên là:

1. Sửa test setup/teardown và đóng tài nguyên.
2. Tách fixtures, test data và file paths theo worker.
3. Dùng `@TempDir`/test framework isolation.
4. Nếu bất khả kháng, thử giảm `forkEvery` để giới hạn state leakage.
5. Chỉ tăng parallelism sau khi chứng minh tests không cạnh tranh shared state.

`forkEvery` là **biện pháp quản lý isolation/resource reuse**, không chữa nguyên nhân gốc của một test thay shared global state.

### 10.4. Lập ngân sách memory cho CI

Ví dụ CI runner có 4 GiB RAM; build sử dụng:

- Gradle daemon heap: 1 GiB (chưa tính native).
- Hai Test workers: tối đa 512 MiB heap mỗi worker.
- Java compiler, Kotlin daemon (nếu có), Metaspace và OS.
- Database/Testcontainers/Docker sidecars nếu integration tests dùng chúng.

Tổng này có thể chạm memory limit dù mỗi `maxHeapSize` riêng lẻ rất “nhỏ”. Khi thấy exit code 137 hoặc process bị kill, kiểm tra **OOM killer/container memory event**, không chỉ tăng Java heap.

## 11. Logging khi test fail, skip hoặc in stdout/stderr

### 11.1. Log pass events

~~~kotlin
tasks.named<Test>("test") {
    testLogging {
        events("passed", "skipped", "failed")
    }
}
~~~

Thích hợp khi học hoặc test suite nhỏ. Với hàng chục nghìn tests, log mọi pass có thể lớn và khó đọc hơn các failures.

### 11.2. Chỉ xem failures + full exception

~~~kotlin
import org.gradle.api.tasks.testing.logging.TestExceptionFormat

tasks.named<Test>("test") {
    testLogging {
        events("failed")
        exceptionFormat = TestExceptionFormat.FULL
        showExceptions = true
        showCauses = true
        showStackTraces = true
        showStandardStreams = false
    }
}
~~~

Thích hợp CI bình thường; khi có case khó, bật streams/filter test cụ thể.

### 11.3. Log console vs report XML/HTML

Nếu `testLogging.events` không in PASSED methods, **không có nghĩa chúng chưa chạy**. Test task vẫn thu kết quả; HTML/XML reports chứa details tương ứng. Trái lại, bật `showStandardStreams` không tự bật JUnit XML nếu bạn đã tắt report trong cấu hình khác.

### 11.4. testLogging.events không phải listener sửa kết quả

`testLogging` điều khiển **presentation của test events**. Nó không thay thế assertions, không chuyển failed test thành passed và không quyết định framework discovery. Muốn thay test selection, dùng `--tests`, `filter` hoặc JUnit tags; muốn điều khiển execution, dùng các API `Test`/JUnit phù hợp.

### 11.5. Test logging granularity

Gradle có `minGranularity`, `maxGranularity` và `displayGranularity` để điều chỉnh cấp suite/class/method được in. Các mốc có thể khác với parameterized/dynamic tests.

Ví dụ minh họa:

~~~kotlin
tasks.named<Test>("test") {
    testLogging {
        events("failed", "passed")
        minGranularity = 2
        maxGranularity = 3
        displayGranularity = 2
    }
}
~~~

Ý định: ưu tiên hiển thị test class/method thay vì mọi synthetic suite. **Không coi các số 2 và 3 là một chuẩn bất biến** khi JUnit dynamic tests thay đổi hierarchy; kiểm tra report thật trên Gradle version đang dùng.

### 11.6. Log level cho test events khác logging của plugin

Một task plugin có:

~~~kotlin
tasks.register("diagnose") {
    doLast {
        logger.lifecycle("Plugin/task diagnostic")
    }
}
~~~

`logger.lifecycle` thuộc Gradle logging; không liên quan `Test.testLogging.events("failed")`. Các system out/err từ test worker được Gradle thu riêng và gắn với test descriptors khi có thể.

## 12. Chiến lược cấu hình local và CI có chủ đích

Thay vì bật tất cả flags đắt tiền trên mọi lần chạy, có thể tạo profile CI được điều khiển bằng Gradle project property.

Kotlin DSL snippet (giả định Java plugin đã áp dụng):

~~~kotlin
import org.gradle.api.tasks.testing.Test
import org.gradle.api.tasks.testing.logging.TestExceptionFormat

val ciMode = providers.gradleProperty("ci")
    .map(String::toBoolean)
    .orElse(false)

tasks.named<Test>("test") {
    minHeapSize = "128m"
    maxHeapSize = if (ciMode.get()) "512m" else "768m"
    maxParallelForks = if (ciMode.get()) 1 else 2

    testLogging {
        events("failed", "skipped")
        exceptionFormat = TestExceptionFormat.FULL
        showStandardStreams = !ciMode.get()
    }
}
~~~

Chạy local:

~~~bash
./gradlew test
~~~

Chạy CI:

~~~bash
./gradlew test -Pci=true
~~~

Đây là **configuration fragment**, không phải một build script độc lập và không phải cấu hình bắt buộc cho mọi dự án. Nếu cần thay đổi parallelism theo CI CPU/memory, dùng provider hoặc chính sách CI rõ ràng thay vì tự động lấy toàn bộ availableProcessors rồi cấp fork quá nhiều.

Khi build logic dùng `ciMode.get()` lúc cấu hình, Gradle sẽ thấy project property theo cơ chế configuration inputs; nhưng thiết kế cacheable custom tasks nâng cao vẫn cần khai báo những inputs có ảnh hưởng output. Không dùng một biến `CI` tùy tiện làm nguồn bí mật cho test result.

## 13. Groovy DSL tương đương đầy đủ cho test task

Trong `build.gradle` với plugin Java:

~~~groovy
plugins {
    id 'java'
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
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

def testProfile = providers.gradleProperty('testProfile')
    .orElse('local')

tasks.named('test', Test) {
    useJUnitPlatform()

    minHeapSize = '128m'
    maxHeapSize = '512m'
    jvmArgs '-Ddemo.jvm.flag=enabled'
    systemProperty 'demo.test.profile', testProfile.get()

    testLogging {
        events 'passed', 'skipped', 'failed'
        showStandardStreams = true
        exceptionFormat = 'full'
        showExceptions = true
        showCauses = true
        showStackTraces = true
    }
}
~~~

Với `settings.gradle`:

~~~groovy
rootProject.name = 'gradle-test-config-lab'
~~~

Ba file Java của mục 7 không đổi. Đây là **phương án Groovy DSL thay thế** cho Kotlin DSL, không nên giữ đồng thời `build.gradle` và `build.gradle.kts` làm hai cấu hình cạnh tranh khi bạn chỉ muốn một script.

Trong Groovy, `events 'passed', 'skipped', 'failed'` và `exceptionFormat = 'full'` là Groovy DSL notation; Kotlin dùng `events(...)` và enum `TestExceptionFormat.FULL` để rõ kiểu.

## 14. Khi có nhiều Test tasks trong project

Nhiều project có unit tests, integration tests, functional tests hoặc test suites tùy plugin.

### 14.1. Cấu hình chung mọi Test task

~~~kotlin
tasks.withType<Test>().configureEach {
    maxHeapSize = "512m"
    testLogging {
        events("failed", "skipped")
        exceptionFormat = TestExceptionFormat.FULL
    }
}
~~~

`TestExceptionFormat` cần import tương ứng ở đầu script. Với `configureEach`, một Test task được đăng ký sau cũng nhận cấu hình. Nó **không tự tạo** `integrationTest` source set hay Test task mới.

### 14.2. Override riêng integrationTest

~~~kotlin
tasks.named<Test>("integrationTest") {
    maxHeapSize = "1g"
    maxParallelForks = 1
    systemProperty("demo.test.profile", "integration")
}
~~~

Đoạn này **chỉ hợp lệ khi task tên `integrationTest` đã được một plugin hoặc build logic đăng ký trước**. Nếu project mẫu ở mục 7 chỉ có Java plugin, lệnh `tasks.named<Test>("integrationTest")` sẽ fail vì không có task đó. Không chép snippet như một project runnable độc lập.

### 14.3. Multi-project build

`tasks.withType<Test>().configureEach` trong một `build.gradle.kts` chỉ điều khiển **Test tasks thuộc project đó**. Nếu app có `:app:test` và library có `:library:test`, cấu hình tại app không tự thay đổi library.

Có thể chia sẻ cấu hình bằng convention plugin hoặc build logic mà các subprojects áp dụng. Không nên đặt `allprojects { ... }` tùy tiện nếu team dùng isolation/configuration cache và convention plugins hiện đại.

## 15. Test properties và tính tái lập của kết quả

### 15.1. Một config sai có thể khiến test “pass giả”

Ví dụ test đọc:

~~~java
String mode = System.getProperty("demo.test.profile", "local");
~~~

Nếu CI quên forward `-PtestProfile=ci`, test âm thầm chạy bằng `local`. Vì thế trong các integration tests quan trọng, nên **assert expected mode** hoặc bắt buộc khai báo property nếu không có default hợp lệ.

Ví dụ assertion tường minh khi environment phải là CI:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

// Bên trong một @Test method trong test class đã khai báo:
assertEquals("ci", System.getProperty("demo.test.profile"));
~~~

Đây là fragment minh họa, không phải Java program độc lập. Chỉ dùng khi pipeline đã cố định input profile là CI.

### 15.2. Dùng system properties quá rộng có thể tạo test coupling

Một configuration như:

~~~kotlin
tasks.named<Test>("test") {
    systemProperties(System.getProperties().mapKeys {
        it.key.toString()
    })
}
~~~

là **anti-pattern**: nó có thể forward vô số properties của Gradle daemon sang test worker, làm test phụ thuộc hidden state, vô tình đưa secret vào process, gây collision với Java runtime properties và làm test khó tái lập.

Ưu tiên **allowlist những keys cụ thể**:

~~~kotlin
tasks.named<Test>("test") {
    systemProperty("demo.test.profile", "ci")
    systemProperty("feature.alpha", "on")
}
~~~

Không chuyển nguyên `System.getenv()` sang `systemProperties(...)` trong production CI vì cùng lý do.

### 15.3. Không in secrets

Nếu token được cấp qua property để test external service, đừng dùng:

~~~java
System.out.println(System.getProperty("api.token"));
~~~

`showStandardStreams=true` và JUnit XML có thể lưu token trong CI artifacts. Thay bằng kiểm tra **có/không**, redact nếu cần, hoặc dùng secret handling của CI và các fixtures cô lập. System properties không phải secret store an toàn.

## 16. Test logging không liên quan trực tiếp tới Java assertions

Java có assertion statement:

~~~java
assert 2 + 2 == 4;
~~~

Khi JVM bật `-ea`, assertion được kiểm tra; nếu tắt, statement có thể không chạy. **JUnit assertions** như `assertEquals(4, 2 + 2)` là phương thức framework và được thực hiện khi test method chạy, không phụ thuộc `-ea`.

Vì vậy:

- `jvmArgs("-ea")` điều khiển **Java language assertions**.
- `useJUnitPlatform()` điều khiển **JUnit test framework discovery/execution**.
- `testLogging.events(...)` điều khiển **cách ghi test events ra console**.
- `assertEquals(...)` thực sự kiểm tra logic trong test.

Đừng dùng `jvmArgs("-ea")` làm biện pháp thay thế JUnit dependency hoặc `useJUnitPlatform()`.

## 17. Kiểm tra JVM configuration thực sự đã có tác dụng

### 17.1. Test worker nhận -D property chưa?

Trong JUnit test:

~~~java
assertEquals("enabled", System.getProperty("demo.jvm.flag"));
~~~

Nếu assertion này pass, property có mặt trong JVM chứa test method. Đó là bằng chứng thực tế mạnh hơn việc chỉ đọc một dòng `jvmArgs`.

### 17.2. Runtime maxMemory không nhất thiết đúng chính xác số Xmx

~~~java
long maxBytes = Runtime.getRuntime().maxMemory();
System.out.println("MAX_HEAP_BYTES=" + maxBytes);
~~~

`maxBytes` phụ thuộc JVM/GC và có thể không bằng đúng 512 × 1024²; không nên khẳng định stdout cố định. Nếu cần test giới hạn, sử dụng **một khoảng hợp lý có tolerance**, xem JVM flags thực tế và giám sát memory.

### 17.3. Dùng jcmd để kiểm tra flags khi cần

Nếu JDK có `jcmd` và policy cho phép attach vào process:

~~~bash
jcmd
jcmd <PID> VM.flags
jcmd <PID> VM.system_properties
~~~

Trong lệnh trên, `<PID>` là placeholder phải thay bằng process ID thật, **không** phải literal cần chạy. `jcmd` có thể cần quyền OS và cùng user; test worker chạy nhanh nên có thể kết thúc trước khi attach.

**Bảo mật:** `VM.system_properties` có thể chứa secret values. Không paste nguyên output vào ticket/public logs nếu chưa kiểm tra. Nếu dùng CI, cân nhắc lấy thông tin cấu hình bằng assertions thay vì attach.

### 17.4. JVM startup failure có thể đến trước mọi JUnit logs

Nếu thêm một flag sai:

~~~kotlin
tasks.named<Test>("test") {
    jvmArgs("-XX:NotARealFlag=1")
}
~~~

test worker có thể fail ngay khi launch với `Unrecognized VM option`. Khi đó `testLogging { events("failed") }` không giúp vì **JUnit test methods chưa được chạy**. Đọc output process startup và Gradle stacktrace; loại bỏ flag sai.

Đây là **cấu hình cố ý sai** để hiểu triệu chứng; không đưa vào project runnable ở mục 7.

## 18. Debug một test failure có mục tiêu

### 18.1. Lọc test rồi tăng log

~~~bash
./gradlew test \
  --tests "demo.CalculatorTest.propertyAndJvmArgReachTestWorker" \
  --rerun-tasks --info
~~~

Ở Windows Command Prompt dùng một dòng:

~~~bat
gradlew.bat test --tests "demo.CalculatorTest.propertyAndJvmArgReachTestWorker" --rerun-tasks --info
~~~

`--rerun-tasks` buộc tasks thực thi lại thay vì chỉ thấy `UP-TO-DATE`. `--tests` lọc đúng test method; `--info` hiển thị nhiều thông tin build và test.

### 18.2. Debug test JVM bằng debugger

~~~bash
./gradlew test --debug-jvm
~~~

Lệnh thường khởi chạy test worker trong chế độ debug và **chờ debugger attach** ở port được Gradle thông báo (thường 5005 cho worker). Nếu không có debugger kết nối, test có thể trông như “treo”.

- Không dùng `--debug-jvm` trên CI thông thường.
- Tránh public network exposure của debug port.
- Hạn chế parallel forks khi debug để tránh tranh port.
- Đây là **debug JVM process** chứ không phải `--debug` logging flag.

### 18.3. Fail fast

~~~kotlin
tasks.named<Test>("test") {
    failFast = true
}
~~~

Khi một failure xảy ra, Gradle cố dừng execution những tests còn lại của task sớm nhất có thể. Nhưng tests đang chạy song song có thể vẫn hoàn tất; không xem `failFast` là cách bảo đảm “chỉ có đúng một test thất bại được chạy”.

Trong CI muốn thu thập **đầy đủ failures**, để `failFast=false` thường hữu ích hơn.

### 18.4. Dry run không kiểm thử logic

~~~kotlin
tasks.named<Test>("test") {
    dryRun = true
}
~~~

Có thể giúp kiểm tra discovery/selection theo framework, nhưng test bodies **không thực thi thực sự**. Do đó `BUILD SUCCESSFUL` ở chế độ này không chứng minh code được kiểm thử. Không dùng `dryRun=true` để “fix” test failures.

## 19. Chẩn đoán lỗi memory và process exit

### 19.1. OutOfMemoryError: Java heap space

Triệu chứng:

~~~text
java.lang.OutOfMemoryError: Java heap space
~~~

Nếu lỗi ném từ **test JVM**, xem:

1. `Test.maxHeapSize` hiện tại.
2. Input data/test fixture có bất thường không.
3. Có memory leak hoặc collection giữ dữ liệu quá lâu không.
4. Test workers có chạy cùng lúc và tranh RAM không.
5. Có thể chia nhỏ test class, giải phóng resources hoặc thêm memory hợp lý không.

Tăng heap từ 256m lên 512m có thể giúp với workload thật sự cần memory, nhưng không chữa memory leak vô hạn.

### 19.2. Metaspace OOM

~~~text
java.lang.OutOfMemoryError: Metaspace
~~~

Metaspace là vùng chứa metadata class, **khác Java heap**. Nâng `maxHeapSize` không bảo đảm khắc phục. Cần xem classloading, dynamic proxies, test frameworks và JVM Metaspace flags nếu có cấu hình giới hạn.

### 19.3. Unable to create native thread

~~~text
java.lang.OutOfMemoryError: unable to create native thread
~~~

Có thể liên quan OS thread/process limits, native memory, số lượng workers/threads quá lớn. Giảm `maxParallelForks`, thread pools, kiểm tra container ulimits và tài nguyên thật; đơn thuần tăng `-Xmx` có thể làm còn ít native memory hơn.

### 19.4. Process finished with non-zero exit value 137

Exit 137 thường gợi ý process bị SIGKILL (ví dụ OOM-killer trong container), nhưng **không đủ bằng chứng một mình**. Kiểm tra logs của CI/container, `dmesg`/events theo quyền có sẵn, memory/CPU limits và process tree. Test worker có thể bị kill **trước khi JVM ném OutOfMemoryError**, nên không có JUnit stacktrace.

### 19.5. Gradle daemon OOM khác test worker OOM

Nếu stacktrace chỉ Gradle daemon heap, cân nhắc `org.gradle.jvmargs` và build logic/tasks. Nếu `Gradle Test Executor` hoặc test worker JVM OOM, sửa `Test.maxHeapSize`, forks và test code. Không đổi cả hai mù quáng.

### 19.6. Forking nhiều workers có thể khiến test chậm hơn

Bộ test có quá ít classes, disk/DB bottleneck hoặc dùng shared locks không được hưởng lợi từ `maxParallelForks=8`. Benchmark ở cùng runner và xem wall time, peak RSS, CPU utilization, stability, failure rate. Quyết định dựa trên phép đo.

## 20. Những hiểu lầm thường gặp

### Hiểu lầm 1: “org.gradle.jvmargs=-Xmx2g thì test cũng có 2 GiB”

Sai. Gradle daemon JVM và Test worker JVM là hai tầng khác nhau.

### Hiểu lầm 2: “maxHeapSize=512m thì cả process luôn dưới 512 MiB”

Sai. JVM còn Metaspace, stacks, code cache, native/direct memory; có thể nhiều workers song song.

### Hiểu lầm 3: “maxParallelForks=4 thì chỉ có một heap 512m được chia bốn”

Sai. Mỗi test worker là một JVM process có giới hạn heap riêng.

### Hiểu lầm 4: “-PtestProfile=ci tự xuất hiện trong System.getProperty”

Sai. `-P` là Gradle project property; dùng `systemProperty(...)` để forward.

### Hiểu lầm 5: “-Dapp.profile=ci cho Gradle chắc chắn được forward vào test”

Không nên giả định. Cấu hình `Test.systemProperty(...)` tường minh.

### Hiểu lầm 6: “System.getenv và System.getProperty là một”

Sai. Environment variables và Java system properties là hai namespace khác nhau.

### Hiểu lầm 7: “jvmArgs là program args”

Sai. JVM options đứng trước main class; program args là thứ khác, `Test` chạy framework worker.

### Hiểu lầm 8: “showStandardStreams = true sẽ in mọi pass event”

Sai. Standard streams và PASSED event là những loại event khác nhau. Có thể bật streams nhưng chỉ log failures cho outcomes.

### Hiểu lầm 9: “events('passed') khiến test chắc chắn chạy lại”

Sai. Gradle có thể đánh dấu task `UP-TO-DATE`; dùng `--rerun-tasks`/clean test khi cần thực thi lại.

### Hiểu lầm 10: “--stacktrace in mọi stacktrace JUnit đầy đủ”

Không. `--stacktrace` cho Gradle failures; `TestExceptionFormat.FULL` cho test exceptions.

### Hiểu lầm 11: “Bật --debug là cách tốt nhất xem một System.out”

Không cần. `showStandardStreams=true` và `--tests` thường chính xác, ít nhiễu, ít rủi ro lộ thông tin hơn.

### Hiểu lầm 12: “Test task thành công thì HTML report tự động hiển thị console streams”

Report có cấu trúc/điều kiện riêng; đọc `build/reports/tests/test/index.html` và XML, không nhầm report với console output hoặc version settings.

### Hiểu lầm 13: “forkEvery=1 nghĩa một process mới cho mỗi test method”

Không. Ngưỡng tính theo **test classes**; khác JUnit per-method lifecycle.

### Hiểu lầm 14: “Java 17 plugin chạy trên Gradle JDK 21 thì tests chắc chắn chạy JDK 21”

Không. Java toolchain/Test.javaLauncher có thể chỉ định JDK khác.

### Hiểu lầm 15: “JUnit 5 test có @Test là đủ cho Gradle”

Cần `useJUnitPlatform()` và JUnit Jupiter engine/launcher trên runtime classpath. Gradle 9 đặc biệt không nên dựa vào JUnit libraries leak từ Gradle nội bộ.

### Hiểu lầm 16: “Thêm -XX:HeapDumpOnOutOfMemoryError an toàn để CI tự upload”

Heap dumps có thể lớn và chứa secrets; phải quản trị lưu trữ/retention/quyền truy cập.

### Hiểu lầm 17: “Cứ bật failFast để tăng độ tin cậy”

Fail-fast giảm thời gian khi failure đầu tiên nhưng có thể ẩn số lượng failures còn lại trong một lần chạy. Chọn theo mục đích CI.

### Hiểu lầm 18: “Set system property trong test method không ảnh hưởng test khác”

Trong cùng JVM, system properties là **process-global mutable state**. Tests có thể phụ thuộc thứ tự nếu không reset.

## 21. Quy trình chọn cấu hình thực tế

### Bước 1. Xác nhận test framework và runtime

- Kiểm tra `plugins` đã áp dụng `java`/`java-library`/`application` phù hợp.
- Kiểm tra `testImplementation` và `testRuntimeOnly`, JUnit Platform/Jupiter.
- Xác nhận Java toolchain version, Gradle Wrapper và Java compiler.
- Chạy một test tối thiểu trên JDK target.

### Bước 2. Phân loại lỗi

| Dấu hiệu | Cần kiểm tra |
| --- | --- |
| Java heap space | `Test.maxHeapSize`, test fixture, leaks |
| Test executor bị kill | CI container limit, forks/native memory |
| JVM flag unrecognized | Java version và `jvmArgs` |
| System property null | `Test.systemProperty`, Gradle `-P`/`-D` mapping |
| stdout không xuất hiện | `showStandardStreams`, Gradle log level, task có chạy? |
| Chỉ hiện stacktrace ngắn | `TestExceptionFormat`, `showStackTraces` |
| Không tìm thấy tests | `useJUnitPlatform`, engine/launcher, `--tests` filters |
| Test flaky khi parallel | Shared files/ports/properties, `maxParallelForks`/JUnit concurrency |

### Bước 3. Cấu hình tối thiểu trước

Một bộ mặc định tương đối thận trọng:

~~~kotlin
tasks.named<Test>("test") {
    useJUnitPlatform()
    maxHeapSize = "512m"
    maxParallelForks = 1

    testLogging {
        events("failed", "skipped")
        exceptionFormat = TestExceptionFormat.FULL
    }
}
~~~

Import `Test`/`TestExceptionFormat` hoặc tận dụng Kotlin DSL generated accessors theo plugin. Đây là fragment dùng trong project **đã khai báo JUnit runtime dependencies**.

### Bước 4. Quan sát và đo

- Chạy test trên CI runner thật.
- Ghi số tests, wall time, memory use/peak RSS, OOM/killed logs.
- Kiểm tra các properties đã tới đúng test JVM bằng assertions.
- Tăng số forks từ 1 lên 2/4 **nếu** runners có đủ RAM và tests cô lập.
- Điều chỉnh heap theo bằng chứng, không chạy theo cảm giác.

### Bước 5. Chốt chính sách logging

- Developer debug: có thể in pass/stdout cho suite nhỏ.
- CI thường xuyên: log failures/skips, giữ JUnit XML và HTML reports.
- CI failure triage: tạm bật full traces/streams và filter test.
- Không in secrets, không public debug port.
- Chạy test thật, không dùng `dryRun` để giả vờ kiểm thử thành công.

## 22. Bài tập có đáp án

### Bài 1. JVM nào được tăng heap?

~~~kotlin
tasks.named<Test>("test") {
    maxHeapSize = "1024m"
}
~~~

**Đáp án:** Heap tối đa của **mỗi JVM test worker** trong task `test`, không phải heap của Gradle daemon.

### Bài 2. 4 workers có bao nhiêu heap tối đa cộng dồn?

`maxParallelForks=4` và `maxHeapSize="512m"`.

**Đáp án:** Có thể tới khoảng 2 GiB **heap caps cộng dồn**, chưa tính daemon/native/OS. Không mặc định container 2 GiB là đủ.

### Bài 3. System property null

CLI dùng `./gradlew test -PtestProfile=ci` nhưng `System.getProperty("demo.test.profile")` vẫn null.

**Đáp án:** `-P` chỉ tạo project property; cần `Test.systemProperty("demo.test.profile", providers.gradleProperty("testProfile").get())` hoặc mapping tương đương.

### Bài 4. Sự khác biệt của -D

Bạn chạy `./gradlew test -Ddemo.mode=ci`. Có thể mặc định giả định test worker nhận `demo.mode`?

**Đáp án:** Không. Forward bằng `providers.systemProperty("demo.mode")` và `Test.systemProperty("demo.mode", ...)`.

### Bài 5. Cấu hình in stdout

JUnit test gọi `System.out.println("hello")` nhưng console không hiện. Cần cấu hình gì?

**Đáp án:** `testLogging.showStandardStreams = true` hoặc events cho STANDARD_OUT, đồng thời bảo đảm task thực sự chạy và Gradle log level không lọc event.

### Bài 6. Failure stacktrace rút gọn

Test fail nhưng chỉ thấy vài frame. Điều chỉnh gì?

**Đáp án:** `testLogging.exceptionFormat = TestExceptionFormat.FULL`, kết hợp `showStackTraces=true` và `showCauses=true`.

### Bài 7. --stacktrace và exceptionFormat

Lệnh `gradle test --stacktrace` có tự thay `TestExceptionFormat.SHORT` thành FULL?

**Đáp án:** Không nhất thiết; hai cơ chế khác nhau: build failures vs test event exception formatting.

### Bài 8. Lệnh chạy lại đúng test

Test đã `UP-TO-DATE` nhưng cần xem một method.

**Đáp án:**

~~~bash
gradle test --tests "demo.CalculatorTest.propertyAndJvmArgReachTestWorker" --rerun-tasks
~~~

### Bài 9. jvmArgs vs systemProperty

Mục tiêu là đặt `demo.mode=ci` để Java test gọi `System.getProperty`. Cách nào rõ nhất?

**Đáp án:** `systemProperty("demo.mode", "ci")`. `jvmArgs("-Ddemo.mode=ci")` cũng biểu đạt JVM option nhưng kém rõ ý định hơn khi đây chỉ là một property.

### Bài 10. maxHeapSize và -Xmx

Cùng task đặt `maxHeapSize="512m"` và `jvmArgs("-Xmx2g")`. Có nên không?

**Đáp án:** Không. Hai nơi điều khiển cùng giới hạn, gây khó đoán precedence và khó debug. Dùng `maxHeapSize` nhất quán.

### Bài 11. Thay System.setProperty trong test

Test A gọi `System.setProperty("feature", "on")` rồi không reset. Test B có thể thấy không?

**Đáp án:** Có nếu chạy chung JVM. Dùng teardown hoặc thiết kế test không phụ thuộc global mutable state.

### Bài 12. forkEvery=1

Nghĩa là fork một JVM mới cho **mỗi method**?

**Đáp án:** Không. Gradle tính theo số **test classes** xử lý trong worker. Dùng ngưỡng thấp sẽ tăng process startup overhead.

### Bài 13. Test Java 17 độc lập

Lệnh:

~~~bash
java -Xms128m -Xmx512m -ea -Ddemo.test.profile=ci -Ddemo.jvm.flag=enabled -cp out demo.HeapProbe
~~~

Với class `HeapProbe` ở mục 7, stdout là gì?

**Đáp án:**

~~~text
mode=ci
flag=enabled
assertions=true
~~~

### Bài 14. App property từ CLI

Chạy project lab `gradle test -PtestProfile=ci --rerun-tasks`. Payload stdout/stderr trong logs là gì?

**Đáp án:**

~~~text
TEST_PROFILE=ci
JVM_FLAG=enabled
~~~

Đây là hai dòng do test method in, không phải toàn bộ Gradle console output.

### Bài 15. OutOfMemoryError: Metaspace

Tăng `maxHeapSize` có bảo đảm sửa lỗi?

**Đáp án:** Không. Metaspace nằm ngoài Java heap; kiểm tra classloading, Metaspace caps và memory configuration phù hợp.

### Bài 16. Exit 137 trong CI

Test process bị kill với exit code 137, không có Java `OutOfMemoryError`. Kết luận gì?

**Đáp án:** Nghi OOM-killer/SIGKILL hoặc external kill, nhưng cần xác minh container/system events; kiểm tra total memory, forks, daemon và native overhead.

### Bài 17. Lỗi JUnit 5 discovery

Có `@Test` Jupiter nhưng Gradle không chạy tests. Hai nhóm cấu hình cần kiểm tra?

**Đáp án:** `useJUnitPlatform()` của `Test` và đúng JUnit Jupiter engine/Platform launcher trên test runtime classpath; thêm kiểm tra source set và `--tests` filters.

### Bài 18. Thay đổi test logging có làm test pass không?

**Đáp án:** Không. Test logging chỉ thay console presentation. Test outcome đến từ framework execution/assertions và Gradle reports.

## 23. Tờ ghi nhớ

| Cần làm | Cấu hình/lệnh |
| --- | --- |
| Heap ban đầu của test JVM | `minHeapSize = "128m"` |
| Heap tối đa của test JVM | `maxHeapSize = "512m"` |
| JVM option riêng của worker | `jvmArgs("-ea")` |
| Property chỉ định cho test JVM | `systemProperty("demo.test.profile", "ci")` |
| Nhiều properties | `systemProperties(mapOf(...))` |
| Lấy Gradle project property | `providers.gradleProperty("testProfile")` |
| Lấy Gradle JVM system property | `providers.systemProperty("demo.mode")` |
| Lấy OS environment variable | `providers.environmentVariable("TEST_MODE")` |
| Chạy JUnit Jupiter | `useJUnitPlatform()` + đúng dependencies |
| In pass/skip/fail | `testLogging.events("passed", "skipped", "failed")` |
| In System.out/err của tests | `testLogging.showStandardStreams = true` |
| In full test exception stacktrace | `exceptionFormat = TestExceptionFormat.FULL` |
| Chạy một method | `gradle test --tests "demo.CalculatorTest.propertyAndJvmArgReachTestWorker"` |
| Buộc chạy lại khi UP-TO-DATE | `--rerun-tasks` |
| Tăng build verbosity | `--info`, `--debug` (cân nhắc secrets) |
| Debug test worker | `gradle test --debug-jvm` |
| Giới hạn forks song song | `maxParallelForks = 2` |
| Fork lại sau N test classes | `forkEvery = N` |
| Heap của Gradle daemon | `org.gradle.jvmargs`, **không** phải Test.maxHeapSize |
| HTML test report | `build/reports/tests/test/index.html` |
| JUnit XML test results | `build/test-results/test/TEST-*.xml` |

**Kết luận:** Cấu hình bộ kiểm thử Gradle đúng bắt đầu từ việc nhận diện **JVM riêng của task `Test`**. Sử dụng `minHeapSize`/`maxHeapSize` cho heap, `jvmArgs` cho JVM flags, `systemProperty` cho cấu hình ứng dụng mà tests đọc, và `testLogging` cho console events/stacktraces. Sau đó điều chỉnh `maxParallelForks` theo memory budget, giữ reports cho CI và kiểm chứng properties/outputs bằng tests chạy thật. **Heap, JVM args, system properties và logging là bốn trách nhiệm khác nhau; điều chỉnh đúng chỗ giúp debug nhanh và tránh test pass giả.**

## 24. Tài liệu tham khảo chính thức

- [Gradle — Testing in Java & JVM projects](https://docs.gradle.org/current/userguide/java_testing.html) — `Test` execution, forked JVMs, JUnit Platform, logging, reports và filters.
- [Gradle — Test task API](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.api.tasks.testing/-test/index.html) — `minHeapSize`, `maxHeapSize`, `jvmArgs`, `systemProperty`, `maxParallelForks`, `forkEvery`.
- [Gradle — TestLogging API](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/testing/logging/TestLogging.html) — events, exception format, stdout/stderr và granularity.
- [Gradle — TestLoggingContainer](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.logging.TestLoggingContainer.html) — logging theo levels và event granularity.
- [Gradle — Logging and Output](https://docs.gradle.org/current/userguide/logging.html) — `--info`, `--debug`, `--stacktrace` và build log levels.
- [Gradle — Build Environment](https://docs.gradle.org/current/userguide/build_environment.html) — Gradle JVM, project/system properties và `org.gradle.jvmargs`.
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html) — Java toolchain và `Test.javaLauncher`.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html) — test source set, `testImplementation`, `testRuntimeOnly`, `test` task.
- [JUnit 5 User Guide](https://docs.junit.org/5.11.4/user-guide/) — Jupiter tests, lifecycle, assertions và JUnit Platform.

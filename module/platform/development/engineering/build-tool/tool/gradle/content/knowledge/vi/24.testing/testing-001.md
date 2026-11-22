# Task Test và mối quan hệ với test, check, build trong Gradle

## 1. Mục tiêu bài học

Trong một dự án Java dùng Gradle, lập trình viên thường chạy ba lệnh `./gradlew test`, `./gradlew check` và `./gradlew build`. Ba lệnh này liên quan chặt chẽ nhưng **không đồng nghĩa**. `test` là task thực thi bộ test được cấu hình; `check` là điểm tập hợp các hoạt động kiểm tra chất lượng; còn `build` là điểm tập hợp cả việc tạo artifact lẫn kiểm tra. Hiểu rõ sự khác biệt giúp tránh tình huống CI báo thành công khi chưa chạy test, hoặc tưởng rằng gọi `test` là đã đóng gói ứng dụng để phát hành.

Bài thuộc nhóm **Kiểm thử** của chủ đề **Build Tool Gradle**. Ví dụ chính sử dụng **Gradle Kotlin DSL**, Java 17 và JUnit Jupiter (JUnit 5), có thể áp dụng tương tự khi dự án dùng Groovy DSL.

Sau bài này, bạn có thể:

1. Phân biệt task kiểu `Test` với task lifecycle `test`, `check`, `assemble`, `build`.
2. Giải thích mặc định quan hệ `check -> test`, `build -> check + assemble` khi dùng Java plugin, và vì sao đây là **task dependencies**, không phải quy tắc thứ tự cố định giữa `assemble` và `check`.
3. Tạo dự án Java 17 với JUnit 5, chạy `test`, `check`, `build` và kiểm tra test reports.
4. Xác định `compileTestJava`, `processTestResources`, `testClasses` và classpath test nằm trong đường chạy task nào.
5. Hiểu `Test.useJUnitPlatform()`, `testImplementation`, `testRuntimeOnly`, JUnit TestEngine và Launcher.
6. Chạy một test class/method cụ thể bằng `--tests`, sử dụng test logging và lọc tags.
7. Giải thích hành vi khi một test fail, test bị skip, task `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE`, hoặc lệnh `-x test`.
8. Tách compiler JVM, Gradle Daemon JVM và **forked JVM thực thi test**.
9. Tích hợp một test suite bổ sung vào `check` bằng cấu hình rõ ràng, thay vì tưởng rằng Gradle tự gom mọi `Test` task.
10. Thiết kế những lệnh phù hợp cho local development và CI, cùng cách chẩn đoán lỗi test.

**Phạm vi:** Mô tả mặc định của Java plugin và Base plugin, cộng những cấu hình minh họa có chủ đích. Kết quả trong một dự án cụ thể có thể thay đổi do plugins khác, custom task dependencies, điều kiện skip, multi-project setup hoặc các tối ưu build cache.

## 2. Phân biệt Test task và lifecycle task

Trong Gradle, một **task** là một đơn vị công việc thuộc task graph. Một task có thể có **actions** (biên dịch, chạy test, tạo JAR) hoặc chỉ đóng vai trò **lifecycle/aggregation**, tức kéo những task khác vào cùng graph bằng `dependsOn(...)`.

| Task | Kiểu / vai trò | Chức năng khi dùng Java plugin |
| --- | --- | --- |
| `compileJava` | `JavaCompile` | Biên dịch source Java production |
| `processResources` | `ProcessResources`/`Copy` | Chép resources của source set main |
| `classes` | Lifecycle | Chuẩn bị classes/resources main |
| `jar` | `Jar` | Tạo JAR từ production outputs |
| `compileTestJava` | `JavaCompile` | Biên dịch source Java của test |
| `processTestResources` | Copy | Chuẩn bị resources test |
| `testClasses` | Lifecycle | Chuẩn bị classes/resources test |
| `test` | **`Test`** | Thực thi tests với framework/launcher và classpath đã cấu hình |
| `check` | **Lifecycle** | Chạy các kiểm tra được gắn vào nó; mặc định Java plugin gắn `test` |
| `assemble` | **Lifecycle** | Tạo artifacts; mặc định Java plugin gắn `jar` |
| `build` | **Lifecycle** | Kết hợp `assemble` và `check` |
| `clean` | `Delete` (do Base plugin) | Dọn build output, không tự chạy trước mọi build |

**Điểm mấu chốt:** `test` là một task thực thi có test classes, runtime classpath và kết quả kiểm thử. `check` và `build` thường **không tự chạy test logic bằng task action riêng**; chúng chọn các task phụ thuộc cần thực thi.

Các lifecycle tasks `assemble`, `check`, `build` do Base plugin cung cấp và Java plugin bổ sung quan hệ mặc định. Với một project chỉ áp dụng Base plugin mà không có Java testing setup, không được giả định đã có task `test`.

### 2.1. Câu hỏi “chạy check có chạy test không?”

**Có, theo mặc định khi áp dụng Java plugin**, vì Java plugin khai báo `check` phụ thuộc vào `test`. Tuy nhiên, test có thể không có source hoặc bị vô hiệu hóa, điều kiện thực thi có thể không thỏa, hay user đã loại task qua `-x test`.

Do đó, “`check` được thực thi” **không đồng nghĩa** chắc chắn đã có N bài test chạy. Muốn xác nhận chất lượng, cần đọc test reports, số lượng tests thực thi và chính sách CI.

### 2.2. Câu hỏi “chạy build có chạy test không?”

**Thông thường có**, vì `build` phụ thuộc `check` và `assemble`, còn `check` phụ thuộc `test`. Một test fail mặc định sẽ làm `test` fail và khiến `check`/`build` fail theo task graph.

Nhưng một số plugin có thể sửa phụ thuộc, hoặc lệnh `./gradlew build -x test` cố ý loại test. Vì thế không thể lấy tên task `build` làm bảo đảm tuyệt đối nếu không kiểm tra graph và settings.

## 3. Task graph mặc định: test, check, assemble, build

Một hình dung tối giản cho một project có Java plugin:

~~~text
:build                      (lifecycle)
  |
  +-- :assemble             (lifecycle)
  |     |
  |     +-- :jar             (sinh JAR)
  |           |
  |           +-- :classes
  |                 +-- :compileJava
  |                 +-- :processResources
  |
  +-- :check                (lifecycle)
        |
        +-- :test           (task kiểu Test)
              |
              +-- :testClasses
              |     +-- :compileTestJava
              |     +-- :processTestResources
              |
              +-- runtimeClasspath của test
                    gồm production outputs, test classes
                    và test dependencies
~~~

Sơ đồ diễn giải **quan hệ phụ thuộc**, không phải lời hứa chính xác về danh sách task hoặc trình tự in log ở mọi Gradle version. Những task có `NO-SOURCE` có thể được đánh dấu tương ứng. Plugins tạo thêm compile/resource/verification/packaging tasks có thể làm graph lớn hơn.

### 3.1. Các quy tắc quan trọng

- `test` cần **compiled test classes** và các artifacts trên test runtime classpath. Gradle tự xác định những producers của classpath cần chạy trước.
- `check.dependsOn(test)` theo convention của Java plugin.
- `assemble.dependsOn(jar)` theo convention của Java plugin.
- `build.dependsOn(assemble, check)` theo Base plugin.
- `build` không nhất thiết chạy `assemble` rồi **sau đó** mới chạy `check`. Nếu hai nhánh độc lập, Gradle có thể chọn thứ tự hoặc chạy song song theo task graph/`--parallel`/plugins.
- Một task xuất hiện ở cả hai nhánh không bị thực thi hai lần trong cùng invocation chỉ vì có nhiều đường phụ thuộc đến nó.

Không nhầm dấu `dependsOn` với `mustRunAfter`/`shouldRunAfter`: `dependsOn` **đưa task phụ thuộc vào graph**; `mustRunAfter` và `shouldRunAfter` chỉ định **thứ tự khi các task đã nằm trong graph**, không tự kéo task mới vào.

### 3.2. Chạy mỗi lệnh thì điều gì xảy ra?

| Lệnh | Công việc theo convention Java plugin | Không nên mặc định suy ra |
| --- | --- | --- |
| `./gradlew test` | Biên dịch nguồn/test cần thiết và chạy `Test` task | Không nhất thiết tạo JAR cuối hoặc chạy mọi quality checks |
| `./gradlew check` | Chạy `test` cùng các verification tasks gắn vào `check` | Không nhất thiết đóng gói JAR |
| `./gradlew assemble` | Tạo artifacts như JAR | Không nhất thiết chạy tests |
| `./gradlew build` | Tạo artifacts và chạy các verification tasks | Không bảo đảm mọi test suite ngoài mặc định đã được gắn vào `check` |
| `./gradlew clean build` | Dọn output rồi dựng lại full build | Không làm cache/download biến mất hoàn toàn; cũng không thay kiểm tra test thực tế |
| `./gradlew build -x test` | Chạy build nhưng **loại task test** | Không đủ điều kiện coi là bản build đã qua unit tests |

Các phần dưới đây minh họa bằng code thật để người học tự kiểm tra.

## 4. Ví dụ dự án Java 17 hoàn chỉnh với JUnit 5

Tạo project Java đơn giản có lớp `Calculator` và bộ unit test. Chúng ta sẽ chạy lần lượt `test`, `check`, `assemble` và `build`, rồi quan sát task graph/báo cáo.

### 4.1. Cấu trúc project

~~~text
test-lifecycle-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── src/
│   ├── main/
│   │   └── java/
│   │       └── demo/
│   │           ├── Calculator.java
│   │           └── Main.java
│   └── test/
│       └── java/
│           └── demo/
│               └── CalculatorTest.java
├── gradlew
├── gradlew.bat
└── gradle/
    └── wrapper/
        ├── gradle-wrapper.jar
        └── gradle-wrapper.properties
~~~

Đây là bài lab cần **Gradle Wrapper hợp lệ**. Nếu project mới hoàn toàn chưa có Wrapper, tạo Wrapper theo quy trình chuẩn của môi trường trước khi chạy `./gradlew`. Cần có/provision được JDK 17 cho Java toolchain và truy cập repository được phép để tải JUnit.

### 4.2. settings.gradle.kts

~~~kotlin
rootProject.name = "test-lifecycle-demo"
~~~

### 4.3. build.gradle.kts hoàn chỉnh

~~~kotlin
plugins {
    java
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
    // BOM phối hợp phiên bản giữa các module JUnit.
    testImplementation(platform("org.junit:junit-bom:5.10.2"))

    // JUnit Jupiter API + engine thông qua aggregate module.
    testImplementation("org.junit.jupiter:junit-jupiter")

    // Launcher được khai báo tường minh trên test runtime classpath.
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    // Kích hoạt JUnit Platform để tìm/chạy JUnit Jupiter tests.
    useJUnitPlatform()

    // Khi kiểm tra ví dụ, hiển thị các test events.
    testLogging {
        events("passed", "skipped", "failed")
    }
}
~~~

**Giải thích:**

1. Java plugin tạo source sets `main` và `test`, các task `compileJava`, `compileTestJava`, `test`, cùng lifecycle tasks liên quan.
2. `testImplementation` dùng cho compile/runtime classpath của test source; nó không tự đẩy JUnit vào JAR production.
3. `platform("org.junit:junit-bom:5.10.2")` thêm BOM constraints để chọn version tương thích của các module JUnit.
4. `org.junit.jupiter:junit-jupiter` là aggregate dependency cung cấp những module JUnit Jupiter cần thiết, gồm test engine tương ứng.
5. `junit-platform-launcher` có trên `testRuntimeClasspath`, giúp tránh dựa vào internal launcher dependencies của Gradle; điều này đặc biệt quan trọng với các bản Gradle hiện đại.
6. `useJUnitPlatform()` chọn framework runner của Test task. Không nên chỉ thêm JUnit dependencies mà quên cấu hình test framework.
7. `testLogging.events(...)` giúp thấy pass/skip/fail theo quy định logging; **không ảnh hưởng việc test được thực thi hay kết quả assertion**.

JUnit version `5.10.2` là một **phiên bản minh họa**, không phải khẳng định nó mới nhất hoặc mặc định nên dùng khi phát hành production. Không cần dùng BOM nếu dự án đã có một cơ chế version alignment khác tương đương.

### 4.4. src/main/java/demo/Calculator.java

~~~java
package demo;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int left, int right) {
        return left + right;
    }
}
~~~

Lớp không có external dependency; nó nhận hai số nguyên và trả tổng.

### 4.5. src/main/java/demo/Main.java

~~~java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(
            "2 + 3 = " + Calculator.add(2, 3)
        );
    }
}
~~~

### 4.6. src/test/java/demo/CalculatorTest.java

~~~java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {

    @Test
    void addsTwoPositiveNumbers() {
        assertEquals(5, Calculator.add(2, 3));
    }

    @Test
    void addsNegativeNumbers() {
        assertEquals(-1, Calculator.add(-3, 2));
    }

    @Test
    void addingZeroKeepsValue() {
        assertEquals(7, Calculator.add(7, 0));
    }
}
~~~

Đây là ba unit tests có assertions thật, không phải ba câu lệnh `println` giả lập kiểm thử. Mỗi method có annotation `@Test` để JUnit Jupiter nhận diện.

### 4.7. Chạy test

macOS/Linux:

~~~bash
./gradlew clean test --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test --console=plain
~~~

**Kết quả mong đợi:** Sau khi biên dịch, Gradle thực thi 3 test methods thành công, tạo test result files và HTML report. Log có thể gồm các dòng task `compileJava`, `compileTestJava`, `test`; với `testLogging`, có thể thấy tên từng test và trạng thái `PASSED`.

Tuy nhiên, **không có một đoạn stdout Gradle cố định** cho mọi phiên bản, shell và môi trường. `CalculatorTest` không in ra `System.out`; điều cần xác minh là **3 tests, 0 failures, 0 errors** trong test report.

### 4.8. Chạy Java main độc lập và đối chiếu stdout

Java plugin không tạo `run` task theo mặc định như Application plugin. Sau khi biên dịch production classes:

~~~bash
./gradlew classes --console=plain
java -cp build/classes/java/main demo.Main
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat classes --console=plain
java -cp build\classes\java\main demo.Main
~~~

**Stdout chính xác của Java chương trình:**

~~~text
2 + 3 = 5
~~~

Điều này tách rõ hai công việc: `classes` **biên dịch source**, còn `test` **chạy JUnit assertions**. Dòng stdout của `Main` không chứng minh rằng ba unit tests đã chạy; muốn kiểm tra test phải chạy `test` và đọc report.

### 4.9. Biên dịch Java thuần bằng JDK 17

Vì `Calculator`/`Main` không phụ thuộc JUnit, bạn cũng có thể chạy:

~~~bash
mkdir -p out
javac -encoding UTF-8 -d out \
  src/main/java/demo/Calculator.java \
  src/main/java/demo/Main.java
java -cp out demo.Main
~~~

Lệnh in `2 + 3 = 5`. Để biên dịch `CalculatorTest` bằng `javac` thuần, bạn còn cần JUnit JARs trên compile/runtime classpath và JUnit Platform launcher; **không** thể chạy JUnit tests chỉ bằng `java demo.CalculatorTest`. Gradle xử lý các dependencies/launcher giúp bạn.

## 5. Dùng cùng project để so sánh test, check, build

Giữ các file ở phần 4, chạy lần lượt các lệnh sau.

### 5.1. Chỉ test

~~~bash
./gradlew test --console=plain
~~~

Công việc chính: chuẩn bị test classes, resolve runtime classpath và chạy `Test` task khi cần. Một lần chạy sau có thể `UP-TO-DATE`, bởi source và các task inputs không thay đổi.

### 5.2. Check

~~~bash
./gradlew check --console=plain
~~~

Theo Java plugin, `check` phụ thuộc `test`; vì vậy Gradle chọn `test` vào graph. Nhưng nếu vừa chạy `test` thành công với inputs không đổi, task có thể hiện `UP-TO-DATE` hoặc `FROM-CACHE`, không nhất thiết thực thi lại test process.

Không nên hiểu `check` là “luôn chạy lại hết test”; nó là **lifecycle aggregation**.

### 5.3. Assemble

~~~bash
./gradlew assemble --console=plain
~~~

Theo Java plugin, `assemble` kéo vào `jar`. Kiểm tra file JAR thường ở:

~~~text
build/libs/test-lifecycle-demo.jar
~~~

Tên thực tế có thể bao gồm project version hoặc cấu hình `archiveFileName` nếu dự án thay đổi. **Assemble không có quan hệ mặc định bắt buộc phải chạy `test`.**

### 5.4. Build

~~~bash
./gradlew build --console=plain
~~~

Theo Base/Java plugin, `build` kéo cả `assemble` và `check`, nên theo convention nó bao gồm việc tạo JAR và kiểm tra tests.

Nếu bạn muốn quan sát **mọi task actions được thực thi lại** trong bài lab:

~~~bash
./gradlew clean build --console=plain
~~~

`clean` xóa build outputs trong project; Gradle vẫn có thể sử dụng dependency cache và những cơ chế cache khác. “Clean build” không có nghĩa tải lại mọi dependency từ internet.

### 5.5. Xem task graph mà không chạy task actions

~~~bash
./gradlew build --dry-run --console=plain
~~~

`--dry-run` cho biết những task nằm trong task graph dự kiến, thường ghi các task `SKIPPED` vì **không chạy actions**. Nó không kiểm tra assertions và không chứng minh tests pass.

**Khác biệt cần ghi nhớ:**
- `--dry-run`: không thực thi các task actions.
- `--test-dry-run`: chế độ Test task mô phỏng selection/execution theo Gradle Test API và tạo test reports mô phỏng; không chạy body của test cases.
- `--tests`: chọn lọc tests nhưng vẫn thực thi các test được chọn.

Không dùng `--dry-run` trong một CI stage nhằm chứng minh code đã được test.

## 6. Khi một test fail, check và build phản ứng thế nào?

Để thử, tạm đổi một assertion của `CalculatorTest`:

~~~java
@Test
void addsTwoPositiveNumbers() {
    assertEquals(6, Calculator.add(2, 3));
}
~~~

`Calculator.add(2, 3)` trả **5**, nên test này **fail** khi nó thực sự được thực thi.

Chạy:

~~~bash
./gradlew clean test --console=plain
~~~

Kết quả mong đợi:

1. `compileJava` và `compileTestJava` có thể thành công.
2. Task `test` chạy JUnit, thấy assertion expected 6 nhưng actual 5.
3. `:test` được đánh dấu **FAILED** theo mặc định.
4. Gradle trả **exit code khác 0**.
5. Test reports chứa failure details và stack trace.

Nếu chạy:

~~~bash
./gradlew clean check --console=plain
~~~

thì `check` không hoàn thành thành công vì task phụ thuộc `test` fail.

Nếu chạy:

~~~bash
./gradlew clean build --console=plain
~~~

thì `build` cũng thất bại. Những tasks thuộc nhánh `assemble` có thể đã hoặc chưa hoàn thành tại thời điểm lỗi, tùy task scheduling. **Không suy luận task `jar` chắc chắn chưa chạy chỉ vì `test` fail**, hoặc ngược lại.

**Khôi phục assertion `assertEquals(5, ...)`** sau bài thử để ba unit tests lại pass.

### 6.1. Gradle tiếp tục gì khi một task fail?

Mặc định Gradle dừng các task chưa chạy không còn thích hợp sau failure. Với:

~~~bash
./gradlew build --continue --console=plain
~~~

Gradle cố chạy **những task khác không phụ thuộc vào task thất bại**, rồi vẫn trả build failure. `--continue` hữu ích khi muốn thu thập nhiều lỗi trong một CI run; nó **không đổi test failure thành success**.

### 6.2. `ignoreFailures` có nghĩa gì?

Có thể cấu hình Test task:

~~~kotlin
tasks.test {
    ignoreFailures = true
}
~~~

Đoạn này chỉ để **giải thích rủi ro**, không nên áp cho CI bắt buộc pass test. Khi bật, Gradle có thể tiếp tục build và báo thành công ở cấp task/build dù có test cases thất bại; test reports vẫn ghi failures.

Nếu đội ngũ cần một quality gate, hãy giữ `ignoreFailures = false` (mặc định) hoặc một policy tương đương. `test`/`check`/`build` chỉ đáng tin khi không bị biến thành “bỏ qua failures”.

### 6.3. `-x test` không phải test pass

~~~bash
./gradlew build -x test
~~~

`-x`/`--exclude-task` loại `test` khỏi task graph, và có thể loại những dependencies chỉ phục vụ `test` nếu không còn task nào cần. Đây không phải một test result `SKIPPED` theo nghĩa mỗi test method bị skip, mà là **task không được chọn chạy**.

Dùng cho trường hợp phát triển nhanh có chủ đích; **không gọi output từ lệnh này là build đã vượt qua unit tests**.

## 7. Cấu hình Test task trong Gradle Kotlin DSL

Trong project Java plugin, có thể cấu hình trực tiếp:

~~~kotlin
tasks.test {
    useJUnitPlatform()

    maxHeapSize = "512m"

    systemProperty("demo.profile", "test")

    testLogging {
        events("passed", "skipped", "failed")
        showStandardStreams = true
    }
}
~~~

Đây là **mảnh mở rộng** cho `build.gradle.kts` của project phần 4, không phải file script độc lập.

- `useJUnitPlatform()`: chạy test engines trên JUnit Platform.
- `maxHeapSize`: giới hạn heap cho **JVM chạy test**, không phải Gradle Daemon.
- `systemProperty`: cung cấp một Java system property cho test process.
- `testLogging`: cấu hình điều gì được ghi ra console. `showStandardStreams = true` cho phép xem output/error streams của test (có thể rất ồn).
- Nếu test dùng resources, environment hay external services, phải cấu hình chúng riêng; Gradle không tự dựng database cho integration tests.

### 7.1. Cấu hình mọi Test tasks

Nếu build có nhiều test suites:

~~~kotlin
import org.gradle.api.tasks.testing.Test

tasks.withType<Test>().configureEach {
    maxHeapSize = "512m"

    testLogging {
        events("failed", "skipped")
    }
}
~~~

`configureEach` là cách cấu hình lazy; những `Test` tasks được tạo thêm sau đó vẫn có thể nhận policy này.

**Phân biệt rõ:** `tasks.test {}` chỉ cấu hình task tên `test` mặc định; `withType<Test>().configureEach` cấu hình **mọi task kiểu Test** trong project, kể cả `integrationTest` nếu nó có kiểu đó.

### 7.2. Test JVM là process khác

Gradle thường chạy tests trong một JVM **forked**, độc lập với Gradle Daemon. Điều này giúp tránh classpath pollution và cho phép cấu hình memory/JVM args riêng:

~~~kotlin
tasks.test {
    maxHeapSize = "1g"
    jvmArgs("-Dfile.encoding=UTF-8")
    systemProperty("app.mode", "test")
}
~~~

Đây là cấu hình **JVM test runtime**. Nó **không thay** `JavaCompile.options.compilerArgs`, không đổi Java source encoding và không thay `org.gradle.jvmargs` cho Daemon.

Khi test dùng charset mặc định, cần cân nhắc behavior của JDK version và hệ điều hành; với file IO có yêu cầu tái lập, nên truyền charset tường minh trong code thay vì dựa hoàn toàn vào `-Dfile.encoding`.

### 7.3. Điều chỉnh số fork

~~~kotlin
tasks.test {
    maxParallelForks = 2
    forkEvery = 0
}
~~~

- `maxParallelForks=2`: cho phép tối đa hai test JVM processes chạy song song đối với Test task (khi có đủ test classes).
- `forkEvery=0`: không áp số test classes tối đa trước khi thay JVM process theo tùy chọn này.
- Tăng parallel forks có thể giảm thời gian nhưng gây race condition khi tests cùng thao tác file, database, port hoặc shared static state.

Không đặt forks quá số CPU/RAM được cấp trong CI. Với những test cần cô lập file tạm, Gradle cung cấp system property `org.gradle.test.worker` để phân biệt worker process khi phù hợp.

### 7.4. Fail-fast

Một số Test tasks hỗ trợ:

~~~kotlin
tasks.test {
    failFast = true
}
~~~

Khi có failure, Test task cố dừng sớm thay vì chạy tất cả tests. Báo cáo chỉ bao gồm những tests thực sự đã chạy. Đây là trade-off giữa phản hồi nhanh và thu thập đủ failures.

Có thể dùng CLI `--fail-fast` cho Test task được hỗ trợ. Với CI cần báo cáo đầy đủ tất cả failures, giữ mặc định `failFast = false`.

## 8. Các dependency của test task

Khi dùng Java plugin, Gradle tạo những configurations thông dụng:

| Configuration | Vai trò |
| --- | --- |
| `implementation` | Dependencies của source production |
| `testImplementation` | Dependencies cần compile/run test |
| `testCompileOnly` | Dependencies chỉ dùng ở lúc compile test |
| `testRuntimeOnly` | Dependencies chỉ cần khi chạy test |
| `testCompileClasspath` | Resolvable compile classpath của test |
| `testRuntimeClasspath` | Resolvable runtime classpath của test |

Project test code thường có thể truy cập production classes và dependencies nhờ Java plugin thiết lập source set/classpath. Test libraries như JUnit không cần đặt trong `implementation` của production.

### 8.1. Vì sao có `testRuntimeOnly` cho JUnit Launcher?

Trong Gradle 9 hiện đại, không nên dựa vào chuyện test runtime classpath vô tình nhận launcher từ Gradle internal dependencies. Nếu dùng JUnit Jupiter:

~~~kotlin
dependencies {
    testImplementation(platform("org.junit:junit-bom:5.10.2"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
~~~

JUnit Jupiter bao gồm API và engine cần thiết; launcher phụ thuộc vào runtime test. BOM đặt version constraints cho các module JUnit. Nếu project dùng test suite DSL, `useJUnitJupiter()` của **suite** tự cấu hình framework dependencies và Test task theo cơ chế khác; đừng trộn hai cách không có chủ đích.

### 8.2. Cách xem runtime classpath

~~~bash
./gradlew dependencies \
  --configuration testRuntimeClasspath \
  --console=plain
~~~

Nếu Gradle báo không tìm được class của test engine/launcher, hãy xem graph, repository và versions trước khi thêm arbitrary dependencies.

### 8.3. Unit test và integration test cần dependencies khác nhau

Unit test thường nhanh, không cần network. Integration test có thể cần database container, messaging service, fixture và timeout khác. Không nên đưa toàn bộ integrations vào `src/test` rồi hy vọng task `test` tự phân loại đúng, hoặc tạo một task `Test` mới mà quên source set và runtime classpath.

Gradle cung cấp JVM Test Suite plugin để mô hình hóa những nhóm test khác nhau; xem phần 12.

## 9. Chỉ chạy một test class hoặc một method

Trong bài lab, có thể chạy:

~~~bash
./gradlew test --tests demo.CalculatorTest --console=plain
~~~

Chạy duy nhất method cụ thể:

~~~bash
./gradlew test \
  --tests demo.CalculatorTest.addsTwoPositiveNumbers \
  --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat test --tests demo.CalculatorTest.addsTwoPositiveNumbers --console=plain
~~~

Khi có nhiều patterns, bạn có thể truyền nhiều `--tests`. Bộ lọc được khai báo trong build script (nếu có) vẫn có thể giới hạn tập test. Đừng dùng command line selection quá rộng và tự cho rằng toàn bộ suite được kiểm tra.

### 9.1. Lọc trong build script

~~~kotlin
tasks.test {
    filter {
        includeTestsMatching("demo.CalculatorTest")
    }
}
~~~

Đoạn này cố định filter cho những lần chạy `test`, kể cả khi được gọi qua `check`/`build`. Nếu chỉ muốn chạy nhanh lúc debug, **ưu tiên `--tests` trên command line** thay vì commit filter khiến CI không còn chạy các test khác.

### 9.2. Lọc theo JUnit Tags

Một ví dụ khi test method có `@Tag("fast")`:

~~~java
package demo;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

class TaggedExampleTest {
    @Test
    @Tag("fast")
    void aFastTest() {
        org.junit.jupiter.api.Assertions.assertTrue(true);
    }
}
~~~

Trong Test task:

~~~kotlin
tasks.test {
    useJUnitPlatform {
        includeTags("fast")
    }
}
~~~

Nếu dùng tag filter, chỉ những JUnit tests phù hợp tags sẽ được chạy. Không giữ cấu hình `includeTags("fast")` trong build chính nếu đội ngũ kỳ vọng `build` bao phủ mọi tests.

### 9.3. Lỗi No tests found for given includes

Nếu user chạy `--tests demo.UnknownTest` mà không có test match, Gradle có thể báo lỗi “No tests found for given includes” thay vì cho rằng test đã pass. Hãy kiểm tra package/class/method, JUnit version và test discovery.

Đừng tắt kiểm tra không tìm thấy test trong CI chỉ để có trạng thái xanh; việc không chạy test cần được phân biệt với chạy và pass.

## 10. Test reports, XML và HTML: kiểm chứng điều gì đã chạy?

Theo cấu hình mặc định phổ biến của Gradle Test task, báo cáo nằm tại:

~~~text
build/
├── reports/
│   └── tests/
│       └── test/
│           └── index.html
└── test-results/
    └── test/
        ├── TEST-demo.CalculatorTest.xml
        └── binary/
~~~

Các đường dẫn là **mẫu mặc định** đối với task `test`, có thể khác nếu project thay `reporting.baseDirectory`, `java.testResultsDir` hoặc cấu hình reports/output paths.

- **HTML:** người đọc mở để xem số tests, thời gian, failures và stack traces.
- **XML JUnit-compatible:** CI servers (Jenkins, GitLab, GitHub Actions qua actions khác, ...) có thể đọc để hiển thị kết quả.
- **Binary results:** được Gradle dùng cho report generation/aggregation.

### 10.1. Không đánh giá kết quả chỉ dựa vào BUILD SUCCESSFUL

`BUILD SUCCESSFUL` cho thấy những task thực thi theo invocation đã thành công theo Gradle policy. Nó **không cho biết** có bao nhiêu test methods được chạy, liệu task `test` có `NO-SOURCE`, bị `-x test`, hoặc có `ignoreFailures=true`.

Để có quality gate tin cậy, CI nên kiểm tra:

1. Task test phù hợp có được chọn không.
2. Có ít nhất số tests kỳ vọng hoặc một cơ chế phát hiện thiếu test phù hợp.
3. Report XML/HTML có số failures/errors bằng 0.
4. Không có flags skip/filter tạm thời trên release pipeline.
5. Những test suites quan trọng ngoài mặc định đã được gắn vào `check`.

### 10.2. Vì sao test stdout không tự hiện?

Gradle có thể capture `System.out`/`System.err` của test để đưa vào reports thay vì luôn in console. Nếu test cố ý in diagnostic:

~~~kotlin
tasks.test {
    testLogging {
        showStandardStreams = true
    }
}
~~~

Chỉ bật khi cần vì output ồn, chậm hoặc chứa thông tin nhạy cảm. Không đưa credentials hoặc dữ liệu khách hàng vào `println` trong test.

### 10.3. Report của test suite khác

Với task `integrationTest`, report thường nằm ở đường riêng như `build/reports/tests/integrationTest/index.html`. Không tìm vào `build/reports/tests/test/index.html` và kết luận integration tests không chạy khi task có report riêng.

Trong multi-project build, các paths tương ứng nằm dưới `module-name/build/...`.

## 11. Test task có thể UP-TO-DATE, FROM-CACHE hoặc NO-SOURCE

Gradle theo dõi inputs/outputs của Test task, gồm test classes, classpath và các cấu hình được đánh dấu làm input. Một invocation không nhất thiết mở test JVM nếu không cần.

| Trạng thái task | Diễn giải | Có thể kết luận 3 tests vừa chạy lại không? |
| --- | --- | --- |
| Không có hậu tố, task executed | Test task thực thi actions trong run hiện tại | Thường có, nhưng cần report |
| `UP-TO-DATE` | Task outputs/inputs vẫn hợp lệ theo Gradle | Không, Gradle tái sử dụng output |
| `FROM-CACHE` | Restore outputs từ build cache hợp lệ | Không, test body không nhất thiết chạy |
| `NO-SOURCE` | Không có test classes/source hợp lệ | Không, có thể chưa có test nào |
| `SKIPPED` | Task được bỏ qua do điều kiện/onlyIf hoặc chế độ khác | Không |
| `FAILED` | Test task hoặc test process thất bại | Có thể đã chạy một phần hoặc nhiều tests; xem report |

Gradle có thể phục hồi kết quả test từ cache khi inputs tương ứng và policy cho phép; với integration tests phụ thuộc database/network thay đổi liên tục, cần cấu hình inputs/outputs và caching policy phù hợp, không tin cache một cách mù quáng.

### 11.1. `clean test` khác `--rerun-tasks`

~~~bash
./gradlew clean test --console=plain
~~~

xóa build outputs trước khi test (vẫn có thể sử dụng cache tùy cấu hình).

~~~bash
./gradlew test --rerun-tasks --console=plain
~~~

yêu cầu các tasks được chọn thực thi lại thay vì coi là up-to-date; không cần xóa mọi build artifacts.

Nếu mục tiêu là chẩn đoán test process thật và tránh cache, có thể kết hợp các tùy chọn phù hợp như `--no-build-cache` tùy chính sách. Không bắt developer chạy lại toàn bộ test suite mỗi invocation khi Gradle có thể tái sử dụng results hợp lệ.

### 11.2. Test không có source

Nếu project không có `src/test/java` hoặc không có test classes hợp lệ, `test` có thể bị `NO-SOURCE`/skip. `check` và `build` vẫn có thể hoàn thành thành công vì không có test thực tế để fail.

Không coi điều này là bug của Gradle; nếu dự án **bắt buộc phải có tests**, bổ sung test count/coverage policy hoặc CI check nhằm phát hiện modules bị thiếu tests.

### 11.3. Test bị @Disabled hoặc @Ignore

JUnit có cơ chế skip test method/classes bằng `@Disabled` hoặc cơ chế tương đương. Khi nhiều tests bị disabled, task `test` có thể thành công trong khi chất lượng kiểm thử giảm. Báo cáo test cần thể hiện skipped count; nên kiểm tra tỷ lệ và lý do disabled tests.

## 12. Thêm integrationTest bằng JVM Test Suite plugin

Các unit tests mặc định là một phần của `check`, nhưng một suite bổ sung **không tự động** trở thành dependency của `check`. Trong Gradle hiện đại, Java plugin tích hợp JVM Test Suite plugin, có `testing` extension và built-in suite tên `test`.

Vì sao cần suite khác?

- Unit tests dùng mock và chạy nhanh.
- Integration tests có thể tương tác nhiều modules, database hoặc network sandbox.
- Functional/e2e tests có thể chậm và chỉ phù hợp stage CI riêng.
- Mỗi suite có dependencies, source directory, timeout và reporting khác nhau.

### 12.1. Cấu hình ví dụ thay thế cho project Java

Đây là **mảnh cấu hình bổ sung** cần project đang áp dụng Java plugin, với test sources phù hợp. Nếu sử dụng thay cách khai báo JUnit ở phần 4, cần chọn **một cơ chế rõ ràng** để quản lý framework dependencies thay vì copy cả hai không kiểm soát.

~~~kotlin
import org.gradle.api.plugins.jvm.JvmTestSuite

testing {
    suites {
        val unitTestSuite = named<JvmTestSuite>("test") {
            useJUnitJupiter()
        }

        register<JvmTestSuite>("integrationTest") {
            // Dùng JUnit Jupiter cho suite riêng.
            useJUnitJupiter()

            dependencies {
                // Suite mới cần dependency tới production code.
                implementation(project())
            }

            targets {
                all {
                    testTask.configure {
                        shouldRunAfter(unitTestSuite)
                    }
                }
            }
        }
    }
}

// Tác động quan trọng: gắn suite bổ sung vào lifecycle check.
tasks.named("check") {
    dependsOn(testing.suites.named("integrationTest"))
}
~~~

Đây là cách dựa trên JVM Test Suite model; có thể dùng task name `integrationTest` ở CLI. `useJUnitJupiter()` ở suite cấp thêm framework dependencies/engine và cấu hình Test task theo convention của suite. Không nhầm với `tasks.test { useJUnitPlatform() }`, vốn chỉ chọn framework trên Test task mà **không tự thêm toàn bộ dependencies**.

### 12.2. Integration test source và ví dụ Java

Với suite tên `integrationTest`, source directory quy ước:

~~~text
src/integrationTest/java/demo/CalculatorIntegrationTest.java
~~~

Nội dung:

~~~java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorIntegrationTest {

    @Test
    void combinedOperationsUseProductionCode() {
        int first = Calculator.add(1, 2);
        int second = Calculator.add(first, 4);
        assertEquals(7, second);
    }
}
~~~

Test này minh họa source set và dependency vào production class, không cần external database. Trong dự án thật, integration tests thường cần thêm môi trường/tài nguyên khác. Không gọi một bài kiểm tra đơn giản là đủ để chứng minh integration của hệ thống lớn.

### 12.3. Các lệnh chạy

~~~bash
./gradlew integrationTest --console=plain
./gradlew check --console=plain
./gradlew build --console=plain
~~~

Sau khi thêm `dependsOn(testing.suites.named("integrationTest"))`:

- Gọi `integrationTest` chỉ chạy suite đó cùng dependencies cần thiết.
- Gọi `check` chạy built-in `test` **và** `integrationTest`.
- Gọi `build` chạy `check` gồm hai suite **cùng** các assemble tasks.
- `shouldRunAfter(unitTestSuite)` sắp xếp khi cả hai suite có mặt, nhưng không kéo `test` vào graph nếu chỉ gọi `integrationTest`.

### 12.4. shouldRunAfter không phải dependsOn

~~~kotlin
testTask.configure {
    shouldRunAfter(unitTestSuite)
}
~~~

Chỉ là ràng buộc **thứ tự ưu tiên** khi tasks cùng nằm trong graph. Nó không buộc integrationTest phụ thuộc trực tiếp vào test. Quan hệ `check.dependsOn(testing.suites.named("integrationTest"))` mới thực sự **đưa integration tests vào check**.

Dùng `shouldRunAfter` thay vì `mustRunAfter` khi muốn Gradle có linh hoạt về scheduling, nếu thứ tự không bắt buộc về tính đúng của hệ thống.

### 12.5. Đặc điểm của extra suites

Một extra suite **không tự có production dependency** như built-in `test` suite, nên cần `implementation(project())` trong suite dependencies để truy cập main output và API của project.

Mặc định một extra suite có conventions về framework và source set; nếu môi trường yêu cầu framework version cụ thể, hãy khai báo rõ và review graph. API JVM Test Suite còn được Gradle ghi nhận là **incubating**; kiểm tra DSL theo Gradle Wrapper trước khi dùng cho convention plugin dài hạn.

## 13. Nếu không dùng JVM Test Suite plugin thì sao?

Một hướng khác là tự tạo source set và task `Test`:

1. Tạo source set, ví dụ `intTest`.
2. Khai báo dependencies cho `intTestImplementation` và `intTestRuntimeOnly`.
3. Cấu hình compile/runtime classpaths đúng.
4. Đăng ký task `Test` có `testClassesDirs`, `classpath` và `useJUnitPlatform()`.
5. Gắn task đó vào `check` nếu muốn nó chạy trong full build.

Một **mảnh mô hình** minh họa bước task (giả định `intTest` đã được tạo/cấu hình đúng):

~~~kotlin
import org.gradle.api.tasks.testing.Test

val intTestSourceSet = sourceSets.named("intTest")

val integrationTest = tasks.register<Test>("integrationTest") {
    description = "Runs integration tests."
    group = "verification"

    testClassesDirs = intTestSourceSet.get().output.classesDirs
    classpath = intTestSourceSet.get().runtimeClasspath
    useJUnitPlatform()
    shouldRunAfter(tasks.named("test"))
}

tasks.named("check") {
    dependsOn(integrationTest)
}
~~~

**Mảnh này không phải file build.gradle.kts độc lập**: cần Java plugin, source set `intTest` tồn tại, dependencies và test engine được cấu hình tương ứng. Với Gradle 9+, custom Test task không mặc định được cấu hình để dùng built-in `test` source set; phải đặt `testClassesDirs` và `classpath` tường minh.

Với project mới, **ưu tiên JVM Test Suite plugin** khi tính năng incubating được cho phép. Mẫu thủ công chủ yếu hữu ích để hiểu các inputs quan trọng của một Test task.

### 13.1. Tại sao không tạo tasks.register<Test> rồi để trống?

Một custom `Test` task không biết classes nào được biên dịch hay library nào nằm trong runtime classpath nếu bạn không cấu hình. Chỉ đặt `useJUnitPlatform()` không làm nó tự tìm được source set.

Tương tự, `tasks.register<Test>("integrationTest")` **không tự gắn vào `check`**; đây là bước độc lập cần thể hiện bằng `dependsOn(...)`.

## 14. Thêm verification task khác vào check

`check` không chỉ dành cho JUnit. Nếu dùng Checkstyle, PMD, SpotBugs hoặc policy checks, plugin có thể gắn những tasks tương ứng vào lifecycle `check`. Cấu hình thực tế tùy plugin.

Bạn cũng có thể tạo một verification task không phải Test. Mẫu minh họa tối giản:

~~~kotlin
val verifyProjectRules = tasks.register("verifyProjectRules") {
    group = "verification"
    description = "Checks a simple project policy."

    doLast {
        val expected = "test-lifecycle-demo"
        require(project.name == expected) {
            "Project name must be $expected"
        }
    }
}

tasks.named("check") {
    dependsOn(verifyProjectRules)
}
~~~

**Đây là ví dụ về wiring**, không phải quality check có giá trị sản xuất. Trong build thực tế, hãy viết các validation tasks có inputs/outputs rõ và tránh truy cập `project` trong task action nếu cấu hình cần tương thích Configuration Cache/Isolated Projects. Một plugin/convention task kiểu chuyên biệt thường phù hợp hơn.

### 14.1. Không đưa mọi task vào build tùy tiện

Nếu muốn thêm một công việc **tạo artifact**, hãy gắn vào `assemble`. Nếu muốn thêm **validation**, gắn vào `check`. `build` đã phụ thuộc cả hai, nên không cần `build.dependsOn(...)` cho mọi task một cách tùy tiện.

Ví dụ logic:

~~~text
New JAR/package producer  -> assemble
New verification task     -> check
Both together             -> build
~~~

Cách này giữ `check` có thể dùng cho quality gate mà không bắt tạo artifact, và `assemble` có thể dùng để tạo artifact nhanh trong vòng lặp phát triển.

## 15. JaCoCo và các quality gates không tự hoạt động như tưởng tượng

Nếu áp dụng JaCoCo plugin:

~~~kotlin
plugins {
    java
    jacoco
}
~~~

Gradle thêm task `jacocoTestReport` và `jacocoTestCoverageVerification` theo những cấu hình plugin phù hợp.

**Nhưng không được suy ra** chỉ chạy `./gradlew build` là có HTML coverage report mới hoặc đã enforce một coverage threshold.

Theo Java/JaCoCo convention:

- `test` có thể thu thập coverage execution data khi JaCoCo được áp dụng.
- `jacocoTestReport` **không tự phụ thuộc vào `test`** theo mặc định.
- `jacocoTestCoverageVerification` **không mặc định là dependency của `check`**.
- Muốn enforce coverage ở CI, phải định nghĩa rule và quan hệ task tương ứng.

Ví dụ wiring cho report:

~~~kotlin
tasks.test {
    finalizedBy(tasks.jacocoTestReport)
}

tasks.jacocoTestReport {
    dependsOn(tasks.test)
}
~~~

Phần này là **mảnh bổ sung** vào build đã áp dụng `jacoco`. `finalizedBy` giúp report task chạy sau test task khi được chọn; `dependsOn(test)` giúp gọi riêng report có test results sẵn. Chi tiết phát sinh reports khi test fail tùy outputs và plugin. Không xem report trống hoặc test `NO-SOURCE` là pass về coverage.

Nếu muốn coverage threshold làm `check` fail, cần cấu hình `jacocoTestCoverageVerification` với violation rules và gắn tường minh vào `check`; đừng giả định chỉ apply plugin là đủ.

## 16. Multi-project build: tên task có scope

Với dự án có nhiều module:

~~~text
root/
├── settings.gradle.kts
├── core/
│   └── build.gradle.kts
├── api/
│   └── build.gradle.kts
└── app/
    └── build.gradle.kts
~~~

Và Settings:

~~~kotlin
rootProject.name = "multi-project-demo"

include(":core", ":api", ":app")
~~~

Gradle task paths có prefix module:

~~~text
:core:test
:api:test
:app:test
:core:check
:api:check
:app:check
:app:build
~~~

Lệnh:

~~~bash
./gradlew :app:test
~~~

nhắm task **test của app project**, cộng những prerequisites cần thiết từ modules phụ thuộc. Nó **không tự có nghĩa chạy :core:test và :api:test**. Nếu app phụ thuộc core, Gradle có thể chạy `:core:compileJava` hoặc `:core:jar` để cung cấp artifact, nhưng điều đó không chứng minh core unit tests đã chạy.

Lệnh:

~~~bash
./gradlew :app:build
~~~

nhắm lifecycle build của app và những task dependencies tương ứng. Nếu CI cần test/quality gate của **tất cả modules**, cần task selection phù hợp, ví dụ `./gradlew build` từ root trong convention đa module hoặc một aggregate task đã khai báo.

**Hãy kiểm tra task paths thực tế**, vì cách `gradle build` từ root chọn các task có tên matching trong subprojects phụ thuộc cấu trúc multi-project và invocation context.

### 16.1. Module chưa có Java plugin

Một subproject không có Java plugin sẽ không có cùng bộ `test`, `compileTestJava`, `jar` tasks như project Java. Không nên viết scripts cho mọi module mà giả định task `:module:test` tồn tại.

### 16.2. Test report nằm dưới build directory mỗi module

~~~text
core/build/reports/tests/test/index.html
app/build/reports/tests/test/index.html
~~~

Không mở root `build/reports/tests/test` rồi kết luận mọi module đã có kết quả.

## 17. Groovy DSL tương đương

Trong project dùng `build.gradle` Groovy DSL, mẫu cấu hình JUnit Jupiter:

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
    testImplementation platform('org.junit:junit-bom:5.10.2')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    testLogging {
        events 'passed', 'skipped', 'failed'
    }
}
~~~

Với ba Java source files ở phần 4, các lệnh `gradlew test`, `gradlew check`, `gradlew build` có cùng ý nghĩa task graph. Không cần giữ đồng thời `build.gradle` và `build.gradle.kts` trong một project.

### 17.1. Groovy: gắn custom verification vào check

~~~groovy
tasks.register('verifyProjectRules') {
    group = 'verification'
    doLast {
        assert project.name == 'test-lifecycle-demo'
    }
}

tasks.named('check') {
    dependsOn tasks.named('verifyProjectRules')
}
~~~

Đây là demo wiring, không phải production-ready validation, và cần xem Configuration Cache compliance trước khi áp dụng cho dự án lớn.

## 18. CI: chọn test hay check hay build?

Không có một lệnh duy nhất đúng cho mọi stage. Dưới đây là cách suy nghĩ theo yêu cầu đầu ra.

| Stage | Lệnh thường dùng | Lý do |
| --- | --- | --- |
| Dev sửa unit test | `./gradlew test --tests ...` | Phản hồi nhanh đúng test đang sửa |
| Dev chạy tất cả unit tests | `./gradlew test` | Không cần JAR package nếu chỉ xác nhận logic |
| PR verification | `./gradlew check` | Bao gồm unit tests và quality gates đã gắn vào `check` |
| PR full build | `./gradlew build` | Vừa sản xuất artifacts vừa chạy checks |
| Release pipeline | `./gradlew clean build` cùng release-specific checks | Tạo artifact và xác thực test/quality gates trước publish |
| Quick packaging | `./gradlew assemble` | Tạo artifact; **không đủ để tuyên bố tests pass** |
| Chẩn đoán task graph | `./gradlew build --dry-run` | Xem selected tasks, không thực thi test |

Trong CI thực tế, **lệnh là một phần của policy**, không thay thế việc kiểm tra results. Nếu team yêu cầu integration tests, security scan, static analysis hoặc coverage, cần gắn explicit vào `check` hoặc thêm stage riêng theo chủ đích.

### 18.1. Một đoạn CI shell đơn giản

~~~bash
set -e

./gradlew --version
./gradlew clean build --console=plain
~~~

Nếu unit test fail, exit code khác 0 khiến shell job fail. CI nên giữ và xuất bản reports XML/HTML theo chính sách, nhưng không cần chạy lệnh `test` rồi ngay sau đó `build` nếu chỉ muốn cùng một bộ test: `build` đã kéo `check` -> `test` theo convention.

### 18.2. Chạy test và build trong cùng một Gradle invocation

~~~bash
./gradlew test build --console=plain
~~~

Đây thường là dư thừa với Java plugin vì `build` đã phụ thuộc `test`, nhưng Gradle sẽ không thực thi `test` hai lần trong **cùng task graph** chỉ vì task được yêu cầu trực tiếp và gián tiếp. Có thể đơn giản hóa thành `./gradlew build` nếu không có lý do đặc biệt.

### 18.3. Không để `-x test` lọt vào release pipeline

`./gradlew build -x test` có thể hữu ích khi developer chỉ kiểm tra packaging trong vòng lặp nhanh. Nhưng nếu lệnh này được copy vào CI release, artifact có thể được phát hành **không có unit test gate**. Cần rà soát commands của CI và rules về skipped tests.

### 18.4. CI fail nhưng developer máy cá nhân pass

Những nguyên nhân thường gặp:

- JDK toolchain, locale, timezone khác.
- Test runtime classpath hoặc repository khác.
- Test chia sẻ file/port/database tạo race condition.
- `maxParallelForks` hoặc workers khác.
- Test phụ thuộc time/clock/network không được kiểm soát.
- Gradle cache làm local không thực thi test lại, trong khi CI chạy trên clean worker.
- Test suite chưa được gắn vào `check` ở một môi trường hoặc plugin version khác.

Đừng bắt đầu bằng `ignoreFailures=true` hoặc tắt test; hãy tái hiện với `clean test`, đọc reports và kiểm soát environment.

## 19. Những nhầm lẫn phổ biến về vòng đời test

| Nhầm lẫn | Thực tế | Hướng xử lý |
| --- | --- | --- |
| `test`, `check`, `build` là ba tên của cùng một task | Một task Test + hai lifecycle aggregators | Xem `dependsOn` và `--dry-run` |
| Gọi `test` luôn tạo JAR | Test chủ yếu chuẩn bị/test classes và runtime deps | Dùng `assemble`/`build` để tạo artifact |
| Gọi `assemble` luôn chạy unit tests | Java plugin không gắn `test` mặc định vào assemble | Dùng `check`/`build` |
| Gọi `check` luôn chạy lại test bodies | Task có thể `UP-TO-DATE`/`FROM-CACHE` | Đọc reports, rerun có chủ đích |
| Gọi `build` luôn chạy integrationTest mới tạo | Extra suite không mặc định nối check | `check.dependsOn(...)` |
| `shouldRunAfter(test)` khiến test được chọn | Ordering rule không phải dependency | Dùng `dependsOn` nếu muốn kéo task vào graph |
| Gradle Test tự thêm JUnit Engine chỉ vì `useJUnitPlatform` | Test task selection không tự thêm mọi framework libs | Khai báo test dependencies hoặc dùng suite DSL |
| `testImplementation` giống production `implementation` | Chỉ áp cho test classpaths | Không đưa JUnit vào production runtime |
| `BUILD SUCCESSFUL` đảm bảo có tests | Có thể NO-SOURCE/skip/ignoreFailures | Kiểm tra test counts và settings |
| `-x test` chỉ đánh dấu mọi test SKIPPED | Loại task khỏi graph | Không coi là test pass |
| Test fail thì chắc chắn không có JAR | Nhánh assemble có thể đã chạy | Xem task graph, không suy diễn thứ tự |
| Test task làm mọi quality checks | Checkstyle/JaCoCo/integration tùy wiring | Gắn đúng tasks vào check |
| JaCoCo coverage verification tự là check dependency | Không mặc định | Cấu hình rules và dependsOn rõ |
| Test stdout không hiện nghĩa test không chạy | Output có thể được capture | Đọc report hoặc bật testLogging |
| Chạy `:app:build` chắc chắn test tất cả subprojects | Task paths theo project | Chạy đúng module tasks/gates |
| Custom Test task tự biết source set | Không phải luôn, nhất là Gradle 9+ | Set testClassesDirs/classpath hoặc dùng Test Suite |
| Test fail khi lọc --tests | Filter không match/classpath/JUnit discovery | Kiểm tra package/method/launcher |
| Dùng nhiều fork luôn nhanh hơn | Tests có thể tranh chấp shared resources | Benchmark, cô lập resources |
| Test `NO-SOURCE` là một bài test pass | Không có test class được chạy | Bổ sung tests và policy phát hiện |

## 20. Quy trình xử lý một lỗi test task

Khi nhận lỗi `Execution failed for task ':test'`, nên đi từ nguyên nhân có thể kiểm chứng.

### Bước 1. Xác định test task nào fail

Trong multi-project, `:app:test` khác `:core:test` và khác `:app:integrationTest`. Đọc task path từ thông báo lỗi, không chỉ nhìn chữ “test”.

### Bước 2. Mở test report

Với Java project mặc định:

~~~text
build/reports/tests/test/index.html
build/test-results/test/
~~~

Đọc test class/method, assertion, stack trace và số skipped tests. Nếu task fail trước khi có report vì JVM không khởi động, xem stack trace của Gradle/test worker.

### Bước 3. Chạy lại đúng test

~~~bash
./gradlew test \
  --tests demo.CalculatorTest.addsTwoPositiveNumbers \
  --console=plain
~~~

Nếu cần loại cache/up-to-date trong điều tra:

~~~bash
./gradlew clean test --console=plain
~~~

### Bước 4. Kiểm tra test runtime classpath

~~~bash
./gradlew dependencies \
  --configuration testRuntimeClasspath \
  --console=plain
~~~

Nếu test engine hoặc launcher thiếu, kiểm tra `testImplementation`, `testRuntimeOnly`, `useJUnitPlatform()` và JUnit versions.

### Bước 5. Kiểm tra environment

Test worker có đúng JDK, timezone, encoding, system properties, network isolation, database fixture và quyền file hay không? Nếu dùng `maxParallelForks > 1`, thử giảm fork và cô lập shared files để tìm race conditions.

### Bước 6. Kiểm tra task wiring

Nếu `integrationTest` không xuất hiện khi chạy `check`, xem cấu hình `dependsOn`. Nếu task custom báo no source, xem `testClassesDirs` và `classpath`. Nếu `build` không chạy test, kiểm tra `-x test`, `enabled=false`, `onlyIf` và `ignoreFailures`.

### Bước 7. Sửa nguyên nhân, không che failure

Không thay assertion expected sai, tắt kiểm tra, bỏ test khỏi graph hoặc bật ignoreFailures chỉ để CI xanh. Nếu test thực sự flaky, cô lập external dependencies, dùng stable fixtures và thu thập đủ diagnostics trước khi áp dụng retry policy.

## 21. Bài tập tự kiểm tra và đáp án

**Câu 1.** `./gradlew test` có mặc định chạy task `check` không?

**Đáp án:** Không. Theo Java plugin convention, `check` phụ thuộc `test`, chứ `test` không phụ thuộc ngược lại vào `check`. Gọi `test` không tự chạy tất cả quality checks gắn ở `check`.

**Câu 2.** `./gradlew check` có tạo JAR như `assemble` không?

**Đáp án:** Không mặc định. `check` tập trung validation; nhánh tạo artifact thuộc `assemble`.

**Câu 3.** `./gradlew build` phụ thuộc vào những lifecycle tasks nào?

**Đáp án:** `assemble` và `check`; với Java plugin, `check` còn phụ thuộc `test`, `assemble` phụ thuộc `jar`.

**Câu 4.** Nếu `test` fail, lệnh `build` có thể báo thành công không?

**Đáp án:** Bình thường không. Tuy nhiên có thể có cấu hình làm nhẹ hoặc bỏ qua failure như `ignoreFailures=true`, `-x test`, `enabled=false` hoặc quality gate bị chỉnh; cần kiểm tra.

**Câu 5.** `--dry-run` có thực thi unit tests không?

**Đáp án:** Không. Nó mô phỏng task graph và bỏ qua task actions, khác `--test-dry-run` chuyên cho dry-run selection của Test task.

**Câu 6.** `build -x test` có được coi là build đã qua tests?

**Đáp án:** Không. `test` bị loại khỏi graph, nên không có unit test result mới bảo đảm.

**Câu 7.** Vì sao lần thứ hai chạy `check` thấy `test UP-TO-DATE`?

**Đáp án:** Gradle thấy inputs/outputs của Test task phù hợp với lần trước, nên có thể dùng kết quả cũ. Không có nghĩa `check` đã bỏ quan hệ phụ thuộc test.

**Câu 8.** JUnit 5 test có `@Test` nhưng Gradle không phát hiện. Cần xem gì?

**Đáp án:** Test source directory, `testImplementation` JUnit Jupiter, runtime engine/launcher, `tasks.test { useJUnitPlatform() }`, package/class name và filters.

**Câu 9.** Khi tạo `integrationTest` suite mới, có tự được `check` chạy không?

**Đáp án:** Không. Cần nối `check.dependsOn(testing.suites.named("integrationTest"))` hoặc dependency tới test task tương ứng.

**Câu 10.** `shouldRunAfter(test)` và `dependsOn(test)` khác nhau thế nào?

**Đáp án:** `shouldRunAfter` chỉ đề xuất thứ tự khi cả hai đã được chọn; `dependsOn` đưa test vào task graph làm prerequisite.

**Câu 11.** Chạy `./gradlew :app:test` có chạy `:core:test` không?

**Đáp án:** Không tự động chỉ vì app phụ thuộc core. Nó có thể chạy compile/JAR của core phục vụ classpath, nhưng không cần chạy core unit tests nếu không được wiring rõ.

**Câu 12.** HTML test report nằm ở đâu?

**Đáp án:** Thường là `build/reports/tests/test/index.html` của project chứa task `test`; vị trí có thể được tùy biến.

**Câu 13.** `testLogging.events("passed")` có làm assertions khác đi không?

**Đáp án:** Không. Nó thay đổi **logging events** ở console, không đổi JUnit discovery hoặc test behavior.

**Câu 14.** Vì sao Java plugin dùng Test task trong forked JVM?

**Đáp án:** Để cô lập tests khỏi Gradle Daemon, giảm classpath contamination, cho phép memory/JVM args độc lập và hỗ trợ parallel forks.

**Câu 15.** Có nên bật `ignoreFailures = true` trong CI để pipeline không chặn release?

**Đáp án:** Không nếu release yêu cầu test pass. Nó có thể che failure ở cấp task/build; CI cần coi lỗi test là blocker hoặc có exception policy được phê duyệt rõ.

**Câu 16.** Chỉ áp JaCoCo plugin có tự làm `build` kiểm tra coverage threshold không?

**Đáp án:** Không. Coverage verification không mặc định được nối vào `check`; phải định nghĩa threshold và task dependency rõ.

## 22. Checklist áp dụng thực tế

1. Xác định project có Java plugin hay không; chỉ Base plugin không tự có `test`.
2. Đặt Java code trong source set main, JUnit tests trong source set test.
3. Khai báo framework dependencies và launcher rõ ràng; bật `useJUnitPlatform()` khi dùng Jupiter.
4. Chạy `./gradlew test` khi cần phản hồi nhanh cho unit tests.
5. Chạy `./gradlew check` khi muốn tất cả validations đã được gắn vào check.
6. Chạy `./gradlew assemble` để tạo artifact và biết rằng nó không mặc định test.
7. Chạy `./gradlew build` để tạo artifact cùng check, không suy luận thứ tự assemble/check.
8. Dùng `--dry-run` để xem graph, nhưng không coi kết quả là quality proof.
9. Đọc HTML/XML reports, kiểm tra số test methods pass/fail/skip.
10. Với extra suites, gắn rõ `check.dependsOn(integrationTest)` và cấu hình classpath/framework.
11. Trong multi-project, dùng task paths như `:app:test`, `:core:check` đúng scope.
12. Không đưa `-x test`, `ignoreFailures=true` hoặc filters tạm thời vào release CI một cách vô ý.
13. Cân nhắc memory/parallel forks dựa trên resource CI và mức độ cô lập của tests.
14. Dùng Gradle Wrapper và JDK toolchain phù hợp; không trộn test runtime JVM với Gradle Daemon.
15. Đối chiếu version-specific Gradle docs, nhất là khi dùng JVM Test Suite API incubating hoặc Gradle 9+ custom Test tasks.

**Công thức nhớ nhanh:**

~~~text
test       -> chạy test cases được cấu hình
check      -> test + các verification tasks khác đã được nối vào
assemble   -> tạo artifact, không mặc định chạy unit tests
build      -> assemble + check
-x test    -> loại test khỏi graph, không phải "đã pass"
integrationTest (custom) -> chỉ vào check nếu cấu hình dependsOn
~~~

## 23. Tài liệu chính thức

1. Gradle — Testing in Java & JVM projects: https://docs.gradle.org/current/userguide/java_testing.html
2. Gradle — Java Plugin, source sets và lifecycle tasks: https://docs.gradle.org/current/userguide/java_plugin.html
3. Gradle — Base Plugin, assemble/check/build: https://docs.gradle.org/current/userguide/base_plugin.html
4. Gradle — JVM Test Suite Plugin: https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html
5. Gradle — Test Task API: https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/testing/Test.html
6. Gradle — Build Lifecycle and Task Graphs: https://docs.gradle.org/current/userguide/build_lifecycle.html
7. Gradle — Gradle Command-Line Interface: https://docs.gradle.org/current/userguide/command_line_interface.html
8. Gradle — JaCoCo Plugin: https://docs.gradle.org/current/userguide/jacoco_plugin.html
9. Gradle — Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
10. JUnit 5 — User Guide: https://junit.org/junit5/docs/current/user-guide/

Các liên kết `current` có thể mô tả bản Gradle mới hơn Wrapper của project đang dùng. Với một repository thật, cần đối chiếu **Gradle Wrapper version**, JDK, testing framework versions, các plugins đang áp dụng và task graph thực tế trước khi xác nhận lệnh `build`/`check` có đủ mọi quality gates theo yêu cầu của tổ chức.
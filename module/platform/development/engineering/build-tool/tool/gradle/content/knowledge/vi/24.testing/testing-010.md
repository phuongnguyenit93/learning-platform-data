# Test thất thường, chạy lại bằng plugin phù hợp và chẩn đoán nguyên nhân trong Gradle

## 1. Test thất thường (flaky test) là gì?

Một **flaky test** là kiểm thử có thể **PASS hoặc FAIL khi chạy cùng mã nguồn và cùng điều kiện đầu vào được cho là tương đương**, không có thay đổi chức năng phần mềm giải thích kết quả khác nhau. Ví dụ:

- Lượt đầu `./gradlew test` thất bại, lượt chạy lại thành công.
- Test luôn PASS khi chạy riêng nhưng đôi lúc FAIL trong cả suite.
- Laptop PASS, CI runner thỉnh thoảng FAIL.
- Chỉ FAIL khi bật parallel execution hoặc khi máy đang quá tải.
- Test fail khi chạy lúc nửa đêm/timezone khác, hoặc khi repository/service trả dữ liệu thay đổi.

**Không phải mọi lỗi “chạy lại thì hết” đều flaky do test.** Build cũng có thể lỗi vì repository tạm mất mạng, compiler khác JDK, container khởi động chưa sẵn sàng hoặc artifact cache bị hỏng. Cần xác định **Gradle task nào** lỗi, **test case nào** lỗi và **nguyên nhân thực tế** trước khi thêm retry.

Một test được tin cậy nên cho kết quả tương ứng với hành vi sản phẩm, không phụ thuộc thứ tự chạy, thời gian máy, tình trạng mạng, trạng thái của test khác hoặc tài nguyên còn sót. Rủi ro của flaky tests:

1. CI báo đỏ ngẫu nhiên, lãng phí thời gian debug và làm chậm review.
2. Developer quen với việc “rerun đến khi xanh”, làm mất niềm tin vào kiểm thử.
3. Lỗi race condition hoặc vi phạm isolation thực sự bị giấu dưới retry.
4. Test không cho biết liệu một thay đổi phần mềm có phá chức năng hay không.
5. Release pipeline có thể phát hành code chứa lỗi nếu “PASS ở lần cuối” được xem là đủ.

**Chiến lược đúng:** thu thập bằng chứng → cô lập test → kiểm soát số lần retry bằng plugin thích hợp → ghi nhận mọi lần FAIL → tìm và sửa nguyên nhân → loại bỏ retry đặc thù khi đã ổn định.

## 2. Phân biệt ba cách “chạy lại”

| Cách | Đơn vị chạy lại | Công cụ | Mục đích |
| --- | --- | --- | --- |
| **Rerun task** | Toàn bộ task `test` và các task dependencies được điều phối bởi Gradle | `./gradlew test --rerun-tasks` | Tái thực thi test task, không bị UP-TO-DATE che đi |
| **Retry failed tests** | Những test cases FAIL trong test task, theo giới hạn | Plugin `org.gradle.test-retry` | Quan sát và giảm tác động ngẫu nhiên có giới hạn |
| **Repeated execution** | Chạy nhiều lần theo vòng lặp hoặc `@RepeatedTest` của framework | Script/CI/JUnit | Kích hoạt flaky behavior để đo tần suất và điều tra |

Ba cơ chế **không tương đương**:

- `--rerun-tasks` **không tự retry một testcase FAIL ngay trong lần test task đang chạy**; nó làm Gradle chạy lại tasks bất chấp up-to-date checks.
- Test Retry Plugin **không tự gọi cả lệnh `./gradlew test` lần nữa**; nó hỗ trợ retry những failed tests trong cùng Test task theo chính sách.
- JUnit `@RepeatedTest(100)` là cách framework tạo nhiều repetitions của một test, **không phải** một plugin tự retry chỉ những tests FAIL.
- Cờ `--continue` chỉ cho Gradle tiếp tục các task độc lập đủ điều kiện sau lỗi, **không** retry test.
- `ignoreFailures = true` làm build ít bị chặn hơn nhưng **không sửa được lỗi** và có thể che tín hiệu đỏ.

Nên dùng “rerun toàn task” khi **đang điều tra**; dùng Test Retry Plugin khi cần chính sách **retry bounded, báo cáo từng attempt và theo dõi flaky** trên CI. Không dùng retry để biến test deterministic FAIL thành PASS giả.

## 3. Dấu hiệu và nhóm nguyên nhân thường gặp

| Nhóm nguyên nhân | Dấu hiệu | Ví dụ cụ thể |
| --- | --- | --- |
| Timing / race condition | PASS khi debug từng bước, FAIL dưới tải | Một thread chưa khởi tạo xong, test `Thread.sleep(50)` rồi assert |
| Shared mutable state | Chạy riêng PASS, cả suite FAIL | Static Map, singleton, fake clock, cache, DB rows không reset |
| Ordering dependency | Chạy đổi thứ tự cho kết quả khác | Test B giả định Test A đã tạo tài khoản |
| Parallel interference | Chỉ fail khi nhiều workers | Cùng port 8080, cùng temp file, DB schema dùng chung |
| External service | Fail khi mạng/API/service chậm hoặc thay đổi | DB chưa ready, HTTP 503, token hết hạn |
| Data/environment | Fail trên một runner/timezone | Locale, `TZ`, encoding, file separator, DST |
| Clock/randomness | Fail gần ranh giới hoặc theo seed | `LocalDate.now()`, random UUID, random order |
| Resource leak | Test sau FAIL, retry đôi khi PASS | Socket/file handle/thread/executor không đóng |
| Test framework misuse | Setup/teardown không đúng | `@BeforeAll` state dùng chung, mock không reset |
| Process boundaries | Chỉ fail khi fork JVM khác | State `static` không tồn tại sau fork, in-memory cache |
| Build configuration | Chỉ fail khi cache/scope khác | Test/runtime dependencies lệch, JDK/toolchain khác |
| Test code thật sự sai | Fail lặp lại nhất quán | Assertion không đúng business rule |

Một test từng FAIL rồi PASS có thể bị tác động bởi **mã production** hoặc **test harness**. Đừng đổ lỗi cho “CI yếu” nếu chưa có dữ liệu.

## 4. Quy trình chẩn đoán trước khi thêm plugin

### Bước 1 — Xác định test task và failure gốc

Ví dụ task trong project đơn:

~~~bash
./gradlew test --stacktrace --console=plain
~~~

Multi-project:

~~~bash
./gradlew :service:test --stacktrace --console=plain
~~~

Quan sát:

- Gradle task `test` có chạy thật hay `UP-TO-DATE`/`FROM-CACHE`?
- Là failure của test assertion, JVM crash, compilation, dependency resolution hay timeout của CI?
- Tên fully qualified class/method, exception, expected/actual, stack trace đầu tiên?
- Có hiện tượng “Test worker process finished with non-zero exit value” hoặc OOM?
- Có failure từ `@BeforeEach`/`@AfterEach`/`@BeforeAll` hoặc resource cleanup?

`--stacktrace` giúp Gradle in exception của build; test stack trace và method names thường chi tiết hơn trong **HTML/XML test reports**. Không paste nguyên CI logs có secrets/URLs chứa token lên issue công khai.

### Bước 2 — Đọc test report trước khi đổi cấu hình

Với Gradle Java plugin, đường dẫn thông thường:

~~~text
build/reports/tests/test/index.html
build/test-results/test/TEST-<test-class>.xml
~~~

Đây là đường dẫn theo convention; nếu đổi `reports`/`layout.buildDirectory` thì có thể khác. XML/HTML giúp tìm test name, retry attempts, failure messages, stack traces, durations và stdout/stderr khi được bật. Không dựa chỉ vào dòng BUILD FAILED.

### Bước 3 — Chạy riêng test bị nghi

~~~bash
./gradlew test --tests "demo.CalculatorTest" --rerun-tasks --no-build-cache
~~~

Chọn method cụ thể nếu cần:

~~~bash
./gradlew test --tests "demo.CalculatorTest.addsPositiveNumbers" --rerun-tasks --no-build-cache
~~~

`--tests` là **task option** do Gradle Test task hỗ trợ, dùng pattern class/method tương ứng với framework. Nếu chạy từ root multi-project, dùng task path rõ ràng:

~~~bash
./gradlew :service:test --tests "com.example.OrderTest"
~~~

**Kết luận hữu ích:**

- Fail khi chạy riêng → nguyên nhân có thể ở chính test, production code, external service hoặc environment.
- Chỉ fail khi chạy cùng suite → ưu tiên kiểm tra shared state, task order, parallel/resource contention.
- Chỉ fail ở CI → kiểm tra runner/JDK/OS, timezone/locale, available resources, container/network/credentials.

### Bước 4 — Chạy lặp có kiểm soát

Một lần PASS không chứng minh đã ổn định. Hãy tái hiện cùng test nhiều lượt trong môi trường an toàn, ghi số lần PASS/FAIL và điều kiện mỗi lượt. Trong bash:

~~~bash
for i in 1 2 3 4 5; do
    echo "Attempt $i"
    if ./gradlew test --tests "demo.CalculatorTest" \
         --rerun-tasks --no-build-cache --console=plain; then
        echo "PASS attempt $i"
    else
        echo "FAIL attempt $i"
    fi
done
~~~

Trong PowerShell:

~~~powershell
1..5 | ForEach-Object {
    Write-Output ("Attempt " + $_)
    & .\gradlew.bat test --tests "demo.CalculatorTest" --rerun-tasks --no-build-cache --console=plain
    if ($LASTEXITCODE -eq 0) {
        Write-Output ("PASS attempt " + $_)
    }
    else {
        Write-Output ("FAIL attempt " + $_)
    }
}
~~~

**Các đoạn script chỉ mang tính chẩn đoán**, không thay thế test report và không tạo một CI gate đúng nếu chỉ trả về exit code của lượt cuối. Nếu cần CI step thất bại khi bất kỳ attempt nào fail, thu thập số thất bại và exit nonzero ở cuối. Đừng dùng vòng lặp vô hạn, nhất là tests tác động database, thanh toán hoặc external services.

### Bước 5 — Thay một biến mỗi lần

Những phép thử có ích:

- `maxParallelForks = 1` so với cấu hình parallel hiện tại.
- JUnit Jupiter parallel execution on/off.
- Chạy test riêng so với cả suite.
- Chạy cùng JDK/toolchain vendor/version như CI.
- Dùng database container mới so với shared development DB.
- Sử dụng fake clock và fixed random seed.
- Chạy trong một clean workspace không có file từ lượt trước.

Nếu test chỉ ổn khi chạy tuần tự, hãy tìm **tài nguyên đang bị chia sẻ**. Không để `maxParallelForks=1` mãi mà bỏ qua data race.

## 5. Plugin phù hợp: Gradle Test Retry Plugin

Plugin chính thức dành cho trường hợp này có ID:

~~~text
org.gradle.test-retry
~~~

Trên Gradle Plugin Portal, phiên bản `1.6.6` được phát hành ngày 07/09/2026. Ví dụ trong bài pin phiên bản này để có cấu hình cụ thể; khi dùng ở dự án thật, đối chiếu phiên bản Gradle Wrapper, JDK, plugin portal/mirror và chính sách cập nhật dependencies.

**Plugin không tự bật retry chỉ vì được áp dụng.** Bạn phải cấu hình `retry.maxRetries` cho từng Test task. Plugin bổ sung extension `retry` trên tasks kiểu `Test`, hỗ trợ JUnit 4, JUnit Jupiter/JUnit Platform, TestNG, Spock trong những kết hợp/framework versions được tài liệu plugin hỗ trợ. Với framework hoặc custom Test task đặc biệt, kiểm tra compatibility thực tế.

Hành vi tổng quát:

1. Chạy tập tests theo Test task như bình thường.
2. Sau khi các tests thực thi, plugin tìm các failed tests đủ điều kiện.
3. Retry những tests đó, không mặc định chạy lại toàn bộ suite.
4. Dừng khi không còn failed tests, đã dùng hết `maxRetries`, hoặc đạt chính sách `maxFailures`.
5. Đưa thông tin từng attempt vào console và reports theo cơ chế Gradle/plugin.
6. Task PASS/FAIL cuối cùng phụ thuộc các failures còn tồn tại và chính sách đối với tests “passed after retry”.

**Quan trọng:** retry có thể giảm mức độ nhiễu trong CI, nhưng **không sửa nguyên nhân flaky**. Plugin docs cũng yêu cầu kết hợp tracking và khắc phục flaky tests, không chỉ đặt retry rồi quên.

## 6. Các tham số retry cần hiểu chính xác

| Property | Nghĩa | Gợi ý sử dụng |
| --- | --- | --- |
| `maxRetries` | Số lần retry **tối đa sau lần chạy đầu** của một failed test | Nhỏ, ví dụ 1–2 để tránh che lỗi |
| `maxFailures` | Ngưỡng số failed tests trong **mỗi vòng**; đạt ngưỡng thì dừng retry | Bảo vệ khi cả suite/infra hỏng |
| `failOnPassedAfterRetry` | Nếu test đầu FAIL nhưng retry PASS, task vẫn FAIL khi true | Thích hợp cho CI nghiêm ngặt/phát hiện flaky |
| `failOnSkippedAfterRetry` | Nếu FAIL trước rồi SKIP ở retry, task FAIL khi true | Tránh đánh đồng SKIP với PASS |
| `filter { ... }` | Giới hạn classes/annotations có thể retry | Áp dụng có chủ đích cho nhóm test |
| `classRetry { ... }` | Chạy lại cả test class đối với lớp thuộc diện lựa chọn | Khi test có state phụ thuộc giữa methods |

**Làm rõ số lượt:** `maxRetries.set(2)` cho phép **tối đa ba attempts** đối với một test: 1 lần đầu + 2 retries, nếu chưa được dừng bởi policy khác. Nó **không có nghĩa** tổng cộng hai lần.

**Mặc định theo tài liệu plugin:** `maxRetries=0` là không retry; `maxFailures=0` là không đặt giới hạn failures; `failOnPassedAfterRetry=false`, `failOnSkippedAfterRetry=true`. Không nên dựa vào defaults ngầm trong CI quan trọng: hãy cấu hình tường minh theo chính sách.

### 6.1. failOnPassedAfterRetry là lựa chọn chính sách

Giả sử một test có kết quả:

~~~text
Attempt 1: FAIL
Attempt 2: PASS
~~~

- Với `failOnPassedAfterRetry.set(false)`, nếu tất cả failed tests cuối cùng PASS, Test task có thể thành công. Tuy vậy test **đã bộc lộ flakiness**.
- Với `failOnPassedAfterRetry.set(true)`, Test task được đánh dấu FAILED dù lần cuối PASS, giúp CI không âm thầm hợp thức hóa lỗi.
- Nếu tất cả attempts vẫn FAIL, task FAIL bất kể cờ này.
- Nếu `ignoreFailures=true`, chính sách task-level failure có thể bị vô hiệu hóa; không bật tùy tiện để “xanh pipeline”.

Khuyến nghị lúc **điều tra root cause:** bật `failOnPassedAfterRetry=true` để giữ tín hiệu. Nếu doanh nghiệp tạm thời nới CI vì ảnh hưởng release, phải có dashboard/issue tracking, giới hạn retries, expiration date và owner sửa lỗi.

### 6.2. maxFailures không phải số lần retry

Theo plugin docs, `maxFailures` được đánh giá theo **số failures của từng vòng thực thi**. Ví dụ `maxFailures=5`: nếu vòng đầu có ≥5 failed tests thì plugin **không bắt đầu retry**; nó không chờ đủ năm lần retry. Điều này tránh tiêu tài nguyên khi DB/CI infrastructure đang hỏng hàng loạt.

## 7. Demo chạy được: Java 17, JUnit Jupiter và Test Retry Plugin

Demo này tạo test **ổn định** trước để xác minh cấu hình JUnit/plugin. Ta cố tình **không đưa randomness vào mặc định**, vì một bài học không nên khiến learner tưởng rằng test ngẫu nhiên là thực hành tốt.

### 7.1. Điều kiện

- JDK 17 có sẵn hoặc toolchain đã được cấu hình để provision theo policy.
- Gradle Wrapper tương thích JDK/Gradle của dự án.
- Có đường truy cập Gradle Plugin Portal và Maven Central (hoặc mirrors được phê duyệt) khi dependency chưa cache.
- Mã chạy với `Java 17+`. Phiên bản JUnit `5.11.4` là version được pin cho demo, không tuyên bố là latest năm 2026.
- Không cần Docker, database, port cố định hay cloud credentials.

Cấu trúc:

~~~text
flaky-tests-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/
    ├── main/java/demo/
    │   ├── Calculator.java
    │   └── Main.java
    └── test/java/demo/
        └── CalculatorTest.java
~~~

Các scripts Wrapper và JAR phải là Gradle Wrapper hợp lệ, không phải tên file trống tự tạo.

### 7.2. settings.gradle.kts

~~~kotlin
rootProject.name = "flaky-tests-demo"
~~~

### 7.3. build.gradle.kts hoàn chỉnh

~~~kotlin
import org.gradle.api.tasks.testing.logging.TestExceptionFormat
import org.gradle.api.tasks.testing.logging.TestLogEvent

plugins {
    java
    id("org.gradle.test-retry") version "1.6.6"
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
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()

    // Cho phép cô lập nguyên nhân song song trong demo.
    maxParallelForks = 1

    // Retry chỉ các failed tests, tối đa 2 lần thêm.
    retry {
        maxRetries.set(2)
        maxFailures.set(10)
        failOnPassedAfterRetry.set(true)
        failOnSkippedAfterRetry.set(true)
    }

    testLogging {
        events(TestLogEvent.FAILED, TestLogEvent.SKIPPED)
        exceptionFormat = TestExceptionFormat.FULL
    }

    reports.junitXml.apply {
        isOutputPerTestCase = true
        // Giữ từng attempt riêng trong giai đoạn chẩn đoán.
        mergeReruns = false
    }
}
~~~

**Lưu ý cú pháp:**

- `plugins { java }` cung cấp Test task và source sets.
- `id("org.gradle.test-retry") version "1.6.6"` áp dụng plugin bên ngoài, được tải từ plugin repository cấu hình.
- `tasks.test { useJUnitPlatform() }` chọn JUnit Platform cho Jupiter.
- `junit-jupiter` bao gồm API/engine cần dùng theo dependency graph; `junit-platform-launcher` được đặt ở runtime như tài liệu Gradle Java testing hướng dẫn.
- `retry` là DSL được plugin cung cấp, không phải `JavaExec` hoặc Test task core tích hợp của Gradle.
- `maxParallelForks=1` giảm độ nhiễu cho demo, **không chữa race conditions trong ứng dụng**.
- `failOnPassedAfterRetry=true` giữ tín hiệu đỏ khi phát hiện flakiness; bỏ/đổi chính sách này chỉ khi có quyết định CI rõ ràng.
- `mergeReruns=false` để XML chứa từng attempt riêng trong quá trình tìm nguyên nhân.

Trường hợp plugin không resolve: kiểm tra `pluginManagement.repositories` trong settings và proxy/TLS; `repositories { mavenCentral() }` cho app/test dependencies không thay thế plugin repository.

### 7.4. Java source: Calculator.java

~~~java
package demo;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int a, int b) {
        return Math.addExact(a, b);
    }
}
~~~

### 7.5. Java source: Main.java

~~~java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("2 + 3 = " + Calculator.add(2, 3));
    }
}
~~~

### 7.6. JUnit Jupiter test: CalculatorTest.java

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class CalculatorTest {
    @Test
    void addsPositiveNumbers() {
        assertEquals(5, Calculator.add(2, 3));
    }

    @Test
    void addsNegativeNumbers() {
        assertEquals(-3, Calculator.add(-5, 2));
    }
}
~~~

Các assertions này deterministic: input cố định, không dùng clock/network/threads, không có shared mutable state. Chúng là **baseline tốt** để kiểm tra task `test` thực sự hoạt động.

### 7.7. Chạy tests bằng Gradle

Linux/macOS:

~~~bash
./gradlew test --console=plain
./gradlew test --tests "demo.CalculatorTest" --rerun-tasks --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --console=plain
.\gradlew.bat test --tests "demo.CalculatorTest" --rerun-tasks --console=plain
~~~

Với mã đúng và dependencies có thể resolve, hai test methods PASS; Test task thành công. **Không có output stdout cố định từ test methods** vì chúng chỉ assert, không `println`. Gradle console sẽ in task outcomes/BUILD SUCCESSFUL theo version/môi trường.

Nếu muốn xác minh một class/method cụ thể:

~~~bash
./gradlew test --tests "demo.CalculatorTest.addsPositiveNumbers" --rerun-tasks
~~~

### 7.8. Chạy Java source bằng javac/java, không cần JUnit

Để tách vấn đề ứng dụng khỏi Gradle plugin/repository, chạy chỉ hai production files với Java 17:

Linux/macOS:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out \
    src/main/java/demo/Calculator.java \
    src/main/java/demo/Main.java
java -cp out demo.Main
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out src\main\java\demo\Calculator.java src\main\java\demo\Main.java
java -cp out demo.Main
~~~

**Stdout chính xác từ Java Main:**

~~~text
2 + 3 = 5
~~~

Lệnh này **không chạy JUnit tests** và cũng **không kiểm tra Test Retry Plugin**. Nó chỉ cho thấy production code compile/run được, hữu ích nếu Gradle đang fail do plugin resolution hoặc test infrastructure.

### 7.9. Thí nghiệm lỗi deterministic: dùng để kiểm chứng retry, không commit

Trong một **copy tạm** của `CalculatorTest.java`, đổi một assertion thành:

~~~java
@Test
void intentionallyFails() {
    assertEquals(99, Calculator.add(2, 3));
}
~~~

Đây là **snippet thay đổi thử nghiệm**, không có trong demo mặc định. `Calculator.add(2,3)` luôn bằng 5 nên assertion này luôn FAIL; plugin có thể retry nó tối đa theo `maxRetries`, nhưng **không thể biến lỗi deterministic thành PASS**.

Sau quan sát, **xóa đoạn test sai này**; không đưa vào source production/CI. Bài học: retry không phải cơ chế thay đổi kết quả đúng/sai của hàm.

## 8. Mô phỏng flaky để nhận diện, không sao chép anti-pattern vào production

Một test dùng timing không có đồng bộ đáng tin:

~~~java
// ANTI-PATTERN: minh họa code dễ flaky, không dùng trong production.
@Test
void reliesOnSleep() throws InterruptedException {
    java.util.concurrent.atomic.AtomicBoolean finished =
            new java.util.concurrent.atomic.AtomicBoolean(false);

    Thread worker = new Thread(() -> finished.set(true));
    worker.start();

    Thread.sleep(1);
    org.junit.jupiter.api.Assertions.assertTrue(finished.get());

    worker.join();
}
~~~

**Vì sao sai:** sau 1 ms không có gì bảo đảm thread worker đã được OS scheduled. Có thể PASS trên máy nhanh, FAIL khi CPU bị tải. `AtomicBoolean` chỉ làm visibility an toàn; **không bảo đảm tiến độ thread**. Nếu assertion ném exception thì `worker.join()` không được gọi, tạo nguy cơ thread leak trong ví dụ minh họa. Đừng dùng đoạn này làm bài test mặc định.

**Cách đúng hơn:** đồng bộ bằng API điều phối thay vì `sleep`:

~~~java
@Test
void waitsForWorkerResult() throws Exception {
    java.util.concurrent.ExecutorService executor =
            java.util.concurrent.Executors.newSingleThreadExecutor();
    try {
        java.util.concurrent.Future<Integer> future =
                executor.submit(() -> 42);

        int value = future.get(5, java.util.concurrent.TimeUnit.SECONDS);
        org.junit.jupiter.api.Assertions.assertEquals(42, value);
    } finally {
        executor.shutdownNow();
    }
}
~~~

Đây là **snippet JUnit Jupiter**; cần `@Test` import (như file demo) và môi trường có thread scheduling bình thường. Timeout 5 giây là giới hạn hợp lý cho ví dụ nhưng không chứng minh mọi máy sẽ luôn đáp ứng; nếu infrastructure bị treo, test phải FAIL có chẩn đoán. Dùng `Future`/`CountDownLatch`/`CompletableFuture` hoặc async testing utilities theo API thật của ứng dụng.

Một retry giúp phân loại “sometimes works”, nhưng lỗi chờ/scheduling **phải được sửa bằng synchronization, timeout đúng và quản lý executor**.

## 9. Thí nghiệm 1: lỗi do shared mutable state

Một nguyên nhân rất phổ biến là tests dùng chung mutable static state hoặc singleton.

Anti-pattern:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SharedStateTest {
    private static final List<String> ITEMS = new ArrayList<>();

    @Test
    void firstTestAddsItem() {
        ITEMS.add("A");
    }

    @Test
    void secondTestExpectsEmpty() {
        assertTrue(ITEMS.isEmpty());
    }
}
~~~

Code này **không phù hợp để đưa vào demo test mặc định**. Kết quả phụ thuộc thứ tự mà framework chạy methods, sự chia sẻ state và việc test khác đã chạm vào list hay chưa. Chạy method riêng có thể PASS, chạy cả class có thể FAIL.

Cách thiết kế tốt hơn:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class IsolatedStateTest {
    private List<String> items;

    @BeforeEach
    void setUp() {
        items = new ArrayList<>();
    }

    @Test
    void addItem() {
        items.add("A");
        assertEquals(1, items.size());
    }

    @Test
    void startsEmpty() {
        assertEquals(0, items.size());
    }
}
~~~

Mỗi test method nhận một list mới. Trong thực tế, cleanup cần bao phủ DB transaction, cache, message queue, temp files, mock servers và static singleton. Không phải mọi shared resource đều khắc phục chỉ bằng `@BeforeEach`; một hệ thống dùng shared database phải thiết kế isolation ở tầng DB.

### 9.1. Đừng sửa bằng `@TestMethodOrder` khi thực chất tests không độc lập

Ép order có thể giúp tái hiện một workflow test, nhưng nếu hai unit tests độc lập lại phụ thuộc lẫn nhau thì đó là thiết kế sai. `@TestMethodOrder` chỉ phù hợp khi thứ tự là yêu cầu nghiệp vụ của một suite được thiết kế có chủ ý; vẫn cần cleanup/rollbacks và fail diagnostics.

## 10. Thí nghiệm 2: test dùng filesystem/ports chung

Hai test đồng thời ghi cùng đường dẫn:

~~~java
// ANTI-PATTERN: nhiễu giữa các tests/processes.
var path = java.nio.file.Path.of("build/tmp/test/result.txt");
java.nio.file.Files.writeString(path, "test A");
~~~

Nếu test B cũng ghi `result.txt`, kết quả có thể phụ thuộc scheduling. Test còn có thể chịu ảnh hưởng từ file cũ của lượt build trước, đặc biệt nếu task không clean directory này.

JUnit Jupiter `@TempDir` là một lựa chọn tốt cho test cần directory riêng:

~~~java
package demo;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.assertEquals;

class IsolatedFilesTest {
    @TempDir
    Path tempDir;

    @Test
    void writesOwnFile() throws Exception {
        Path file = tempDir.resolve("result.txt");
        Files.writeString(file, "ok");
        assertEquals("ok", Files.readString(file));
    }
}
~~~

Dù có `@TempDir`, file cleanup/external side effects ngoài tempDir vẫn cần quản lý. Với network ports, tránh hardcode `8080` trong mọi test. Nếu framework/server hỗ trợ **port 0 (ephemeral)**, để hệ điều hành cấp port và lấy port thực đang được bind; không “tìm port trống bằng cách mở rồi đóng” trước khi server khởi động vì có race between check and use.

### 10.1. Gradle maxParallelForks không phải JUnit parallel config

`maxParallelForks` điều khiển số forked test JVM processes mà Gradle có thể chạy. JUnit Jupiter còn có các settings parallel execution **bên trong một JVM**. Giảm `maxParallelForks` xuống 1 chỉ giảm một chiều song song, chưa chắc loại bỏ mọi concurrency. Khi điều tra, tắt các tầng parallel độc lập, rồi mở lại có kiểm soát.

## 11. Thí nghiệm 3: clock, timezone, locale và randomness

Anti-pattern phụ thuộc thời gian:

~~~java
// ANTI-PATTERN: ngày hiện tại khác nhau theo thời gian và múi giờ.
assertEquals(
    java.time.LocalDate.of(2026, 11, 9),
    java.time.LocalDate.now()
);
~~~

Cách đúng hơn với business logic phụ thuộc clock: **inject `Clock`**:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class DateServiceTest {
    static LocalDate today(Clock clock) {
        return LocalDate.now(clock);
    }

    @Test
    void usesFixedClock() {
        Clock clock = Clock.fixed(
            Instant.parse("2026-11-09T00:00:00Z"),
            ZoneOffset.UTC
        );
        assertEquals(
            LocalDate.of(2026, 11, 9),
            today(clock)
        );
    }
}
~~~

Test này không phụ thuộc đồng hồ thực; nếu business yêu cầu timezone khác, pin zone thích hợp và test ranh giới DST đúng mục đích. Dự án có code random nên truyền `Random` có seed rõ hoặc fake generator vào logic, không gọi `Math.random()` trong mỗi assertion rồi mong retry sửa được tính ngẫu nhiên.

**Tránh chữa tạm:** tăng `Thread.sleep`, thêm thời gian chờ không có điều kiện, ép `-Duser.timezone=UTC` để giấu logic dùng timezone mặc định ở nơi không nên. Hãy định nghĩa rõ thuộc tính thời gian của API.

## 12. Cấu hình Gradle Test task giúp chẩn đoán

Một Test task có nhiều lựa chọn hữu ích để cô lập nguyên nhân:

~~~kotlin
import org.gradle.api.tasks.testing.Test
import org.gradle.api.tasks.testing.logging.TestExceptionFormat
import org.gradle.api.tasks.testing.logging.TestLogEvent

tasks.named<Test>("test") {
    useJUnitPlatform()

    maxParallelForks = 1
    forkEvery = 0

    testLogging {
        events(
            TestLogEvent.FAILED,
            TestLogEvent.SKIPPED
        )
        exceptionFormat = TestExceptionFormat.FULL
        showStandardStreams = false
    }
}
~~~

**Đây là snippet điều tra thay thế/bổ sung**, không phải config mới chạy song song với demo mà không hòa giải. Giải thích:

- `maxParallelForks` mặc định thường là 1; tăng nó cho phép nhiều forked JVMs và có thể lộ race.
- `forkEvery=0`: không đặt giới hạn số test classes trên một forked JVM. Đặt giá trị nhỏ có thể giúp cô lập static state leak nhưng tăng thời gian test.
- `testLogging` tăng chất lượng thông tin failure; `showStandardStreams` có thể gây lộ dữ liệu nhạy cảm nên mặc định nên tắt, chỉ bật tạm khi đã kiểm tra nội dung.
- `useJUnitPlatform()` cần đúng với test framework và engine mà project sử dụng.
- `failFast` khác retry: khi true có thể dừng sớm sau failed test, giảm tín hiệu tổng thể; không bật khi đang muốn thu thập toàn bộ failures.

### 12.1. Nếu muốn thử forkEvery=1

~~~kotlin
tasks.named<Test>("test") {
    forkEvery = 1
}
~~~

Điều này yêu cầu Gradle tạo test process mới sau số test classes theo cài đặt; có thể làm các lỗi static leak biến mất hoặc giúp khoanh vùng. Nhưng process startup cost rất cao và không giải quyết DB/shared external resources. Dùng nó như **thí nghiệm chẩn đoán**, không mặc định là giải pháp toàn suite.

### 12.2. Khi nào cần nâng timeout?

Một operation bất đồng bộ cần timeout hữu hạn, nhưng tăng timeout từ 1 giây lên 60 giây mà không biết điều kiện hoàn tất chỉ làm pipeline chậm hơn. Thiết kế tốt đợi **một điều kiện có thể kiểm tra**, ví dụ await server health, queue offset, future completion; timeout dùng để fail có thông tin khi điều kiện không được đáp ứng.

## 13. Cấu hình retry có giới hạn cho CI

Plugin retry phù hợp nhất khi có **điểm bắt đầu/điểm kết thúc rõ ràng** và thu thập lỗi. Nếu chỉ muốn retry trên CI, có thể dựa vào biến môi trường `CI` mà CI cung cấp:

~~~kotlin
val ciRetries = providers.environmentVariable("CI")
    .map { 2 }
    .orElse(0)

tasks.test {
    retry {
        maxRetries.set(ciRetries)
        maxFailures.set(10)
        failOnPassedAfterRetry.set(true)
    }
}
~~~

Đây là **snippet thay thế cho giá trị `maxRetries.set(2)` trong demo**, không được paste trùng hai lần rồi giả định cả hai có tác dụng. Nó coi **sự hiện diện** của biến `CI` là dấu hiệu CI; một số runners đặt biến `CI` thành chuỗi rỗng/false hoặc không đặt, vì vậy hãy kiểm tra policy cụ thể. Có thể dùng một Gradle property quản lý bởi pipeline khi muốn tường minh hơn.

Một công thức xử lý chính sách:

- Local development: retry = 0 hoặc 1 để dev thấy lỗi gốc nhanh.
- CI integration: retry tối đa 1–2, giữ log first failure.
- CI release gate: cân nhắc `failOnPassedAfterRetry=true`, hoặc policy quarantine/owner rõ ràng.
- Hạ tầng lỗi diện rộng: `maxFailures` hạn chế retry vô ích.
- Test gây side effects thật (thanh toán, gửi email, mutate shared DB): không bật retry nếu chưa bảo đảm idempotency/cleanup.

Đừng cho phép `maxRetries=100` như cách né thất bại; xác suất cuối cùng PASS có thể tăng mà chất lượng test không tốt hơn.

## 14. filter và classRetry: retry đúng lớp test

Mặc định plugin có thể retry các failed tests đủ điều kiện. Nếu chỉ muốn retry nhóm integration tests:

~~~kotlin
tasks.test {
    retry {
        maxRetries.set(2)
        filter {
            includeClasses.add("*IntegrationTest")
            excludeClasses.add("*NonRetryableIntegrationTest")
        }
    }
}
~~~

`includeClasses`/`excludeClasses` kiểm tra **test class name patterns**, không phải method-level test filter của Gradle `--tests`. Tên phải khớp class identity framework báo về. Với test dùng dynamic/parameterized names, cần xem plugin docs vì cách xác định testcase identity có thể khác.

Nếu một class có tests phụ thuộc shared `@BeforeAll` state hoặc step-wise workflow không thể chạy lại từng method độc lập, plugin có `classRetry`:

~~~kotlin
tasks.test {
    retry {
        maxRetries.set(2)
        classRetry {
            includeClasses.add("*StepWiseIntegrationTest")
        }
    }
}
~~~

Điều này retry **cả class** theo tiêu chí, không phải tự động biến các tests trong class thành độc lập. Ưu tiên **sửa fixture isolation** nếu có thể. Plugin có hỗ trợ filters bằng class-level annotation names cho trường hợp phù hợp, nhưng đừng tưởng JUnit `@Tag` luôn đồng nhất với class annotation filter của retry plugin.

### 14.1. Những trường hợp không được retry mù quáng

- Test tạo payment/order có side effects mà rollback chưa an toàn.
- Test verify migration/schema đang thay DB thật.
- Test phụ thuộc một external rate-limited service; retry có thể làm lỗi nghiêm trọng hơn.
- Test crash do OOM, disk full hoặc JVM abort; retry từng case không giải quyết infrastructure.
- Test có timeout kéo dài khi hệ thống mất kết nối diện rộng.
- Test đã bị chuyển sang `@Disabled` hoặc skipped liên tục, không nên tính là PASS.

Có thể tách các bài integration tests ra task suite riêng và áp chính sách retry lên task đó, tránh bật giống nhau cho unit tests và end-to-end tests.

## 15. Báo cáo retries và hiểu mergeReruns

Gradle xuất test reports thường ở:

~~~text
build/reports/tests/test/index.html
build/test-results/test/TEST-*.xml
~~~

Với Test Retry Plugin, các attempts có thể được thể hiện riêng trong Gradle console/HTML/XML. Gradle có tùy chọn:

~~~kotlin
tasks.test {
    reports.junitXml.apply {
        isOutputPerTestCase = true
        mergeReruns = true
    }
}
~~~

**Điểm dễ sai nhất:** `mergeReruns` là **cách trình bày báo cáo JUnit XML**, **không tự tạo retry**. Khi enabled, một testcase FAIL rồi PASS có thể được biểu diễn với `<flakyFailure>` trong một `<testcase>`, thay vì nhiều testcase/`<failure>` riêng. CI parser khác nhau có thể xem một testcase như PASS hoặc hiển thị flakiness khác nhau.

- `mergeReruns=false` (mặc định) giữ mỗi execution như testcase riêng trong XML; thích hợp khi muốn đọc first failure rõ, nhưng một số CI JUnit parsers có thể tính build failed nếu nhìn thấy failure attempt.
- `mergeReruns=true` có thể làm CI JUnit parser hiển thị pass-on-retry không còn là một failure thông thường; phải bảo đảm công cụ vẫn theo dõi `<flakyFailure>`.
- Nếu `failOnPassedAfterRetry=true`, **Gradle Test task có thể FAIL** dù parser XML đọc combined testcase là PASS; thống nhất CI gate theo exit code + retry reporting policy.
- Nếu test parameterized có display names thay đổi theo random/clock, merge có thể nhóm sai hoặc tách sai testcase. Giữ stable test identity.

Không bật `mergeReruns=true` chỉ vì muốn “CI xanh hơn”. Nếu dashboard không nhận diện flaky failures, cần plugin/parser phù hợp hoặc báo cáo riêng có đầy đủ first-attempt failures.

## 16. Đo tỷ lệ flaky thay vì chỉ đếm build đỏ

Sau khi thu thập reports, có thể tính các chỉ số:

| Chỉ số | Cách hiểu |
| --- | --- |
| **First-attempt failure count** | Số lần test thất bại ngay lần đầu trên các cơ hội chạy |
| **Passed-after-retry count** | Số lần ban đầu FAIL nhưng thành công sau retry |
| **Always-failing count** | Số lần test FAIL đến hết retry budget |
| **Flaky rate** | First-attempt failures / số lần test thực sự được chạy ban đầu |
| **Mean retries used** | Số retries trung bình trên mỗi test invocation |
| **CI rerun cost** | Tổng runtime/compute thêm do retries |
| **Quarantine age** | Số ngày test bị cô lập/chặn khỏi CI gate |

Ví dụ một test chạy ban đầu 200 lần, FAIL 10 lần rồi cả 10 lần retry thành công:

~~~text
First-attempt failure rate = 10 / 200 = 5%
Passed-after-retry cases = 10
Persistent failures = 0
~~~

Không kết luận “test ổn 100%” từ 0 persistent failures. Test này có **5% first-attempt failure rate**, đủ để tác động đáng kể tới CI lớn. Cũng không suy “nguyên nhân do timing” chỉ từ tỷ lệ này; cần stack traces, system metrics, test-order và environment evidence.

### 16.1. Đừng lấy tổng retry attempts làm mẫu số sai

Nếu một test thất bại rồi được retry hai lần, nó có **một initial test invocation và hai extra attempts**, không phải ba lượt CI độc lập. Để so flakiness giữa các tests, cần thống nhất denominator và nhóm theo **class/method/parameters/runner context**.

### 16.2. Ưu tiên lịch sử, không chỉ một run

Một testcase PASS 10 lần liên tiếp vẫn có thể FAIL lần 11. Ghi trend trong CI/build scans/Develocity hoặc hệ thống quản lý test report đã phê duyệt, liên kết với commit, runner/JDK, fork config, seed/clock, test name và first stack trace. Tránh log secrets trong test outputs.

## 17. Root cause: timing/race

Nếu lỗi liên quan thread/async:

1. Tìm `Thread.sleep`, busy waiting, asynchronous callbacks không được await.
2. Kiểm tra data race và missing happens-before giữa threads.
3. Tách condition thực tế cần chờ ra khỏi “đợi đại N milliseconds”.
4. Dùng `CountDownLatch`, `Future.get(timeout)`, `CompletableFuture`, structured concurrency/framework utility phù hợp với JDK/library.
5. Log timestamp **theo monotonic clock** cho latency measurement; không dựa vào wall-clock timestamp để đo duration.
6. Chạy lặp trên CPU load phù hợp để xác minh.
7. Nếu lỗi chỉ xuất hiện khi parallel, kiểm tra mutex, thread safety và shared storage.

**Cảnh báo:** đặt một timeout dài hơn có thể giảm flakiness nhưng chưa sửa race. Sửa điều kiện đồng bộ và lifecycle mới là mục tiêu.

## 18. Root cause: database, filesystem và external services

### 18.1. Database

- Mỗi test nên dùng fixture riêng có unique identifiers.
- Ưu tiên transaction rollback khi framework hỗ trợ; nhưng kiểm tra side effects bất đồng bộ/ngoài transaction.
- Xóa dữ liệu tạo bởi test trong `@AfterEach`/fixture teardown; không phụ thuộc thứ tự tests.
- Với parallel tests, tách schema/database/container hoặc dùng khóa có scope thích hợp.
- Không chạy destructive tests trên shared production DB.

### 18.2. Filesystem

- Dùng JUnit `@TempDir` hoặc unique directories theo test/process.
- Không để test A và B cùng ghi `build/tmp/result.json`.
- Dùng atomic file operations khi cần, không assume filesystem iteration order.
- Đóng streams/handles đúng.
- Trên Windows, file lock behavior có thể khác Linux, nên test cross-platform thực tế.

### 18.3. HTTP / service readiness

- Không giả định container/service “đã sẵn sàng” chỉ vì process khởi động.
- Chờ health/readiness condition có giới hạn và log rõ.
- Dùng mock/stub HTTP khi test business logic không cần network thật.
- Với integration thật, provision service version/ports/data theo policy, tránh gọi public API có rate limit.
- Phân biệt HTTP 503, 401/403, connection refused, DNS, TLS error; retry test case có thể làm thêm load nhưng không sửa credentials/TLS.

### 18.4. Timezone và randomness

- Inject `Clock`, chọn time zone rõ.
- Dùng `Locale.ROOT` khi format case/parse không phụ thuộc ngôn ngữ.
- Pin random seed và log seed khi test thật sự mang tính property-based.
- Tránh assertions “chỉ có một timestamp chính xác” khi code làm việc với scheduler/network có jitter.

## 19. Root cause: JDK, test JVM và CI resources

Gradle Test task chạy tests trong **forked JVM riêng**, không phải JVM Daemon Gradle. Vì vậy so sánh local/CI cần:

- Gradle Wrapper version.
- JDK vendor, version và Java toolchain runtime của test worker.
- JVM options (heap, GC, timezone, `--add-opens`).
- `maxParallelForks` và JUnit parallel execution configuration.
- Container CPU quota, RAM, filesystem, network timeouts.
- System locale, `TZ`, environment variables.
- External services/DB versions và connection pools.
- Dependency versions/lockfiles; test runtime classpath.
- Các test task/plugins khác chạy song song trong multi-project CI.

Có thể bổ sung tạm để xem môi trường **trong test process**:

~~~java
System.out.println("Java: " + System.getProperty("java.version"));
System.out.println("Zone: " + java.time.ZoneId.systemDefault());
System.out.println("Worker: " + System.getProperty("org.gradle.test.worker"));
~~~

Đây là snippet chẩn đoán, **không có output cố định**; Gradle property `org.gradle.test.worker` giúp phân biệt forked test workers. Kiểm tra trước khi log OS paths/credentials. Đừng bừa thay `org.gradle.jvmargs` rồi tưởng đã thay `Test.jvmArgs` của forked JVM; hai lớp runtime khác nhau.

## 20. Groovy DSL tương đương

Đối với dự án dùng `build.gradle`, phần cấu hình plugin/test task tương đương:

~~~groovy
plugins {
    id 'java'
    id 'org.gradle.test-retry' version '1.6.6'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

test {
    useJUnitPlatform()
    maxParallelForks = 1

    retry {
        maxRetries = 2
        maxFailures = 10
        failOnPassedAfterRetry = true
        failOnSkippedAfterRetry = true
    }

    reports {
        junitXml {
            outputPerTestCase = true
            mergeReruns = false
        }
    }
}
~~~

**Chọn một DSL:** `build.gradle.kts` dùng Kotlin và `.set(...)` trên retry properties; `build.gradle` dùng Groovy assignment. Không copy lẫn cú pháp. Plugin version trong bài được pin cho ví dụ, không chứng minh nó phù hợp mọi Gradle Wrapper cũ. Với convention plugins/build logic tập trung, áp dụng retry plugin ở nơi các `Test` tasks thực sự được tạo, không giả định plugin tự có ở mọi subprojects.

## 21. Những sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Chạy lại đến khi xanh, xóa log FAIL | Mất tín hiệu flaky và root cause | Giữ first failure, giới hạn retries, theo dõi issue |
| `--rerun-tasks` được gọi là retry plugin | Rerun toàn task, không chỉ failed tests | Dùng `org.gradle.test-retry` khi cần selective retry |
| `maxRetries=2` được hiểu là hai attempts tổng | Là 1 initial + tối đa 2 retries | Ghi rõ semantics trong CI |
| `maxFailures` được hiểu là số lần retry | Là ngưỡng failed tests mỗi round | Kiểm tra plugin docs |
| Cài plugin nhưng quên maxRetries | Default 0, không retry | Set `retry.maxRetries` cụ thể |
| `failOnPassedAfterRetry=false` và không đo gì | Flaky bị che sau eventual PASS | Dashboard/issue, cân nhắc true trong release gate |
| `ignoreFailures=true` | Bỏ qua test failures trong Gradle | Giữ default false |
| `mergeReruns=true` được nghĩ là tự chạy lại | Chỉ đổi format JUnit XML | Cấu hình plugin/framework retry riêng |
| `--continue` được coi là retry | Chỉ tiếp tục các tasks khác | Dùng đúng công cụ |
| Chỉ PASS khi chạy riêng, kết luận test hết lỗi | Chưa thử shared state/order | Chạy cả suite và cô lập resource |
| Tăng `Thread.sleep` vô hạn | Che race và làm CI chậm | Condition-based synchronization |
| Tắt parallel mãi | Có thể giấu resource sharing bugs | Tách fixtures/ports/files, bật lại sau sửa |
| Dùng `@TestMethodOrder` để che order dependence | Tests vẫn phụ thuộc nhau | Isolation/setup/teardown độc lập |
| Retry test có side effects không idempotent | Có thể tạo dữ liệu/giao dịch trùng | Cleanup/idempotency hoặc không retry |
| Tự ghi binary/JUnit reports vào source | Làm workspace dirty, dễ leak | Gradle report output directories |
| Chỉ nhìn Gradle `--stacktrace` | Có thể thiếu assertion first failure | Đọc Test HTML/XML và test stack traces |
| XML parser báo xanh dù Gradle FAIL | `mergeReruns` và policy không thống nhất | Gate theo exit code + reporting semantics |
| Thấy fail khi chạy trên CI, tự tăng heap | Không phải mọi lỗi là OOM | Thu thập CPU/memory/GC và exception thực |
| CI retries làm kéo dài hàng giờ | Retry budget quá cao | `maxRetries` thấp, `maxFailures`, phân suite |
| Check flakiness một lần rồi đóng ticket | Lỗi có xác suất thấp có thể tái phát | Theo dõi trend và regression test |

## 22. Khi nào quarantine một flaky test?

Đôi khi một test chặn mọi commit, còn sửa root cause cần thời gian. Một biện pháp **tạm thời và có kiểm soát** có thể là quarantine (cô lập) test khỏi release gate nhưng vẫn chạy/ghi report trong job riêng.

Điều kiện tối thiểu:

1. Có issue link và owner rõ ràng.
2. Có lý do đã xác minh hoặc giả thuyết mạnh + dữ liệu.
3. Có ngày hết hạn/quy trình rà soát, không quarantine vô thời hạn.
4. Không quarantine tests che lỗi bảo mật, dữ liệu, thanh toán hoặc chức năng trọng yếu nếu không có phương án kiểm soát rủi ro.
5. Test vẫn được chạy và đo flakiness nếu hạ tầng cho phép.
6. Sau khi sửa, test quay về gate chuẩn, xóa exception/retry riêng.

`@Disabled` có thể làm test biến mất khỏi coverage và che tín hiệu; ưu tiên tách suite/tag/job riêng theo governance được tổ chức duyệt. `ignoreFailures=true` cho cả suite càng dễ che các lỗi khác.

## 23. Quy trình CI mẫu theo ba vòng

### Vòng A — Test run chính

~~~bash
./gradlew test --console=plain
~~~

CI cần lưu Test report artifacts theo retention/access policy; nếu plugin retry đã bật, giữ first failures và thông tin attempts.

### Vòng B — Khi phát hiện flaky, tái hiện targeted

~~~bash
./gradlew test \
    --tests "com.example.order.OrderServiceTest" \
    --rerun-tasks --no-build-cache \
    --info --console=plain
~~~

Tên class là minh họa. Đừng thêm `--info` cho tất cả tasks công khai nếu logs có secrets, HTTP headers hoặc test data nhạy cảm. Chỉ thu thập đủ bằng chứng.

### Vòng C — So sánh môi trường và sửa

- Dùng cùng Git commit, Gradle Wrapper, JDK/toolchain và dependency lock.
- Chạy với parallel=1 để kiểm tra shared state, sau đó bật lại.
- Kiểm tra class fixture, DB isolation, clock/seed, external readiness.
- Khi sửa code, chạy lại cả targeted test và suite đầy đủ nhiều lượt theo chính sách.
- Theo dõi first-attempt failure rate sau sửa, không chỉ “build xanh”.

**Một test pass-after-retry là một quan sát flaky**, không phải bằng chứng root cause đã biến mất.

## 24. Bài tập tự kiểm tra và đáp án

**Bài 1.** `./gradlew test --rerun-tasks` có chỉ chạy lại các failed tests không?  
**Đáp án:** không. Nó yêu cầu rerun tasks (và dependencies theo Gradle model), không chọn từng failed test method.

**Bài 2.** Muốn retry tự động failed tests trong cùng Test task, plugin nào phù hợp?  
**Đáp án:** `org.gradle.test-retry`, cấu hình `retry.maxRetries` cho Test task.

**Bài 3.** `maxRetries.set(2)` nghĩa là tổng cộng tối đa mấy attempts của một testcase?  
**Đáp án:** tối đa 3 (1 đầu + 2 retries), trừ khi policy khác dừng sớm.

**Bài 4.** `maxFailures.set(5)` sẽ làm gì khi vòng đầu có 5 failures?  
**Đáp án:** plugin dừng không bắt đầu retry cho vòng đó theo ngưỡng failures.

**Bài 5.** Test FAIL lần đầu, PASS ở retry, `failOnPassedAfterRetry=true` thì task ra sao?  
**Đáp án:** task được coi FAIL để giữ tín hiệu flaky, nếu không bị các flags bỏ qua failure vô hiệu hóa.

**Bài 6.** `mergeReruns=true` có khiến test tự retry không?  
**Đáp án:** không, nó thay cách ghi lại attempts trong XML.

**Bài 7.** Test chạy riêng PASS nhưng suite FAIL; nhóm nguyên nhân nào đáng xem?  
**Đáp án:** shared mutable state, test order, files/ports/DB, parallel interference, fixture teardown.

**Bài 8.** Vì sao `Thread.sleep(100)` là cách chờ nguy hiểm?  
**Đáp án:** thời gian trôi qua không bảo đảm asynchronous operation đã hoàn thành; dùng synchronization/condition wait.

**Bài 9.** `maxParallelForks=1` có luôn tắt JUnit Jupiter parallel tests trong một JVM không?  
**Đáp án:** không. Hai lớp parallel execution độc lập cần kiểm soát phù hợp.

**Bài 10.** Test phụ thuộc `LocalDate.now()` bị lỗi vào ngày đầu tháng. Hướng sửa?  
**Đáp án:** inject fixed `Clock` trong test, xác định timezone, test ranh giới thời gian cụ thể.

**Bài 11.** Hai tests cùng ghi `result.txt` khi chạy song song có thể xảy ra gì?  
**Đáp án:** race/overwrite/flaky; dùng `@TempDir` và paths riêng.

**Bài 12.** Một test liên tục FAIL do database offline, có nên tăng `maxRetries` từ 2 lên 50?  
**Đáp án:** không; sửa readiness/infra, hạn chế retries và dùng maxFailures.

**Bài 13.** Demo Java 17 khi chạy `java -cp out demo.Main` in gì?  
**Đáp án:** chính xác `2 + 3 = 5`.

**Bài 14.** Demo JUnit Jupiter mặc định có test failures không?  
**Đáp án:** không nếu code và dependencies đúng; hai assertions đều PASS.

**Bài 15.** Lệnh Gradle nào chạy riêng `demo.CalculatorTest`?  
**Đáp án:** `./gradlew test --tests "demo.CalculatorTest"`.

**Bài 16.** Một test dùng `@RepeatedTest(10)` tương đương Retry Plugin không?  
**Đáp án:** không. RepeatedTest chạy nhiều lượt theo framework ngay cả khi không fail; Retry Plugin nhắm tới failed tests sau lượt chạy.

**Bài 17.** Khi thấy “passed after retry”, bạn nên ghi nhận gì?  
**Đáp án:** first failure stack trace, lần retry, commit, runner/JDK, seed/time, nhóm nguyên nhân và issue owner.

**Bài 18.** Tại sao không retry bài test gửi email thực hoặc charge payment nếu chưa có idempotency?  
**Đáp án:** có thể tạo side effects trùng lặp hoặc ngoài kiểm soát.

**Bài 19.** Test worker JVM và Gradle daemon JVM có luôn là một không?  
**Đáp án:** không. Gradle Test chạy trong forked JVM; kiểm tra đúng Java version/JVM opts ở worker.

**Bài 20.** Tình trạng test cải thiện khi `forkEvery=1` nói lên điều gì?  
**Đáp án:** có thể có static/resource leak theo process; vẫn cần xác định nguyên nhân và đánh đổi performance.

**Bài 21.** Vì sao cần giữ initial failure dù cuối cùng PASS?  
**Đáp án:** đó là bằng chứng flaky, giúp phân biệt regression và giảm tình trạng “rerun đến khi xanh”.

**Bài 22.** CI parser chỉ đọc JUnit XML và cho test PASS dù Gradle Test task FAIL. Cần xem gì?  
**Đáp án:** `mergeReruns`, `failOnPassedAfterRetry`, plugin retry semantics và cách CI gate dựa vào task exit code.

**Bài 23.** Lý do `java.lang.AssertionError` khi test luôn FAIL có phải flaky không?  
**Đáp án:** chưa có bằng chứng. Nếu deterministic fail, sửa assertion/production code, retry không giúp.

**Bài 24.** Test timeout khi service mới tạo chưa ready, cần cải thiện gì?  
**Đáp án:** readiness/health condition với timeout hữu hạn, fixture lifecycle và diagnostics trước khi tăng retries.

## 25. Checklist áp dụng thực tế

- [ ] Đã xác định đúng test method, Test task, first failure và stack trace?
- [ ] Có phân biệt Gradle build failure với JUnit assertion failure?
- [ ] Đã đọc HTML/XML reports và lưu chứng cứ an toàn?
- [ ] Biết `--rerun-tasks` khác selective retry plugin?
- [ ] `org.gradle.test-retry` được pin version phù hợp Wrapper/CI?
- [ ] `retry.maxRetries` thấp và `maxFailures` có giới hạn khi cần?
- [ ] `failOnPassedAfterRetry` được chọn rõ theo CI gate policy?
- [ ] `failOnSkippedAfterRetry` không vô tình xem skipped như passed?
- [ ] `mergeReruns`/CI XML parser giữ được flaky signal?
- [ ] Không dùng `ignoreFailures=true` để che lỗi toàn suite?
- [ ] Test có idempotency nếu thực sự bị retry?
- [ ] Có xem test order, shared static state, mutable singletons?
- [ ] Có phân biệt Gradle forks và JUnit internal parallel?
- [ ] Có dùng temporary directories/unique ports/database fixtures?
- [ ] Có loại `Thread.sleep` tùy tiện, thay bằng condition wait?
- [ ] Clock/locale/timezone/random seed được kiểm soát khi có liên quan?
- [ ] Có so đúng Gradle Wrapper, JDK/toolchain và CI runner?
- [ ] Có xử lý resource leaks/cleanup trong `finally`/teardown?
- [ ] Có theo dõi first-attempt failure rate, không chỉ final PASS?
- [ ] Quarantine nếu có phải có owner, issue và expiration date?
- [ ] Tests quan trọng không bị ngưng gate mà thiếu risk acceptance?
- [ ] Sau sửa đã chạy lại targeted test và full suite nhiều lượt?

## 26. Tài liệu chính thức và tham khảo

- [Gradle Plugin Portal — Test Retry Plugin](https://plugins.gradle.org/plugin/org.gradle.test-retry): ID, phiên bản và cấu hình plugin trong `plugins` DSL.
- [Gradle Test Retry Plugin — README](https://github.com/gradle/test-retry-gradle-plugin): retry mechanics, `maxRetries`, `maxFailures`, policy, filters, class retry và reporting.
- [Gradle — Testing in Java & JVM projects](https://docs.gradle.org/current/userguide/java_testing.html): Test task, JUnit Platform, test filtering, forked JVMs, XML reports.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): `--rerun-tasks`, `--continue`, `--tests`, task paths.
- [Gradle — Test DSL](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html): `maxParallelForks`, `forkEvery`, `ignoreFailures`, `testLogging`.
- [Gradle — Best Practices for Testing](https://docs.gradle.org/current/userguide/best_practices_testing.html): test isolation, hiệu năng, môi trường và tổ chức suite.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): `@Test`, `@RepeatedTest`, `@TempDir`, lifecycle và parallel execution.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): chọn JDK cho test/compile workers.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): tương tác giữa cấu hình build và test infrastructure.
- [Gradle — Test Report Aggregation](https://docs.gradle.org/current/userguide/test_report_aggregation_plugin.html): tổng hợp test results khi có nhiều modules.

**Kết luận:** Test flaky là **tín hiệu về vấn đề chưa được hiểu**, không phải lời mời chạy lại vô hạn. Dùng `--tests` để khoanh phạm vi, `--rerun-tasks` để thực thi lại task, và `org.gradle.test-retry` để **retry có giới hạn những failed tests** trong cùng Test task. Giữ first failure, cấu hình `failOnPassedAfterRetry` và JUnit XML reporting theo policy CI, rồi điều tra timing, shared state, parallelism, external services, clock, dữ liệu và môi trường. Mục tiêu cuối là **test ổn định ngay từ lần đầu**, không phải tỷ lệ “xanh sau retry” ngày càng cao.
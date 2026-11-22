# Test retry, flaky test và chính sách xử lý lỗi không ổn định trong Spring Boot

## 1. Vì sao một bài test “đỗ ở lần chạy thứ hai” vẫn là vấn đề?

Trong CI, một ca JUnit có thể thất bại ở lần đầu với timeout, `AssertionError`, `Connection refused` hoặc lỗi dữ liệu, nhưng chạy lại thì thành công mà không sửa code. Việc này thường được gọi là **flaky test**: kết quả của cùng một phép kiểm thử thay đổi giữa các lần chạy trong khi input/code/config dự kiến không đổi.

Flakiness khiến pipeline bị mất độ tin cậy. Developer quen bấm “Rerun job”, reviewer bỏ qua build đỏ, CI tốn thời gian và một bug thật có thể được coi là “chắc lại flaky”. **Retry là một công cụ chẩn đoán/giảm gián đoạn có giới hạn, không phải cách sửa lỗi gốc.**

Trong Spring Boot, nguyên nhân hay gặp là:
- Dùng `Thread.sleep` để đợi `@Async`, scheduler, message queue hoặc HTTP server.
- Phụ thuộc thứ tự chạy JUnit methods/classes, đồng hồ hệ thống, random data hoặc timezone.
- Test chia sẻ `static` state, Spring singleton bean, Mockito mocks, System properties, H2/Redis/Kafka hoặc cùng file path.
- `@Transactional` của test thread không bao phủ transaction ở HTTP/worker thread.
- Testcontainers/DB/broker chưa ready; dùng fixed port hoặc chưa cleanup.
- `@DirtiesContext` làm context bị đóng khi các test song song còn sử dụng nó.
- Network/outbound exporter/backend không ổn định, retry không phân biệt lỗi ứng dụng với hạ tầng.
- CPU/RAM/connection pool ở CI bị quá tải khi tăng `maxParallelForks` hoặc JUnit parallelism.

Bài học thuộc nhóm **Build và CI**, dành cho Java 17+, Spring Boot 3.5.x, JUnit Jupiter, Gradle. Bạn sẽ hiểu cơ chế **Gradle Test Retry Plugin**, phân biệt retry với `@RepeatedTest` và `--rerun-tasks`, cấu hình một chính sách CI không che giấu flaky tests, xây test độc lập có thể chạy lại, đọc reports, quản lý quarantine có chủ sở hữu/hạn xử lý và sửa những nguyên nhân đặc trưng của Spring Boot.

Ví dụ chính dùng **Gradle Test Retry Plugin 1.6.6** (phiên bản được công bố trên Gradle Plugin Portal tháng 9/2026) và Spring Boot **3.5.8**. Mã runnable là một dự án Java/Gradle với business logic, async, `@TempDir` và `@SpringBootTest`. Các tests mẫu đều được thiết kế **ổn định**, không cố ý cài lỗi ngẫu nhiên vào một suite bình thường. Chưa có bằng chứng chạy Gradle/JUnit trong môi trường soạn bài, nên mọi số liệu chạy và kết quả dưới đây là **kỳ vọng theo source**, không phải stdout giả.

## 2. Phân loại thất bại trước khi quyết định retry

Không phải mọi lần “fail rồi pass” đều do chính test code viết sai. Phân loại giúp sửa đúng tầng.

| Nhóm | Dấu hiệu | Retry có thể cho biết gì? | Cách sửa đúng |
|---|---|---|---|
| **Deterministic product bug** | Cùng input luôn cho kết quả sai | Thường vẫn fail; pass đôi khi do state leak | Sửa ứng dụng, thêm regression test |
| **Test flakiness** | Kết quả đổi theo timing/order/seed | Fail→pass là tín hiệu mạnh, chưa đủ tìm nguyên nhân | Sửa synchronization, fixtures, isolation |
| **Intermittent product failure** | Dịch vụ thật đôi khi race/timeout | Rerun pass không làm bug biến mất | Sửa ứng dụng, retry policy nghiệp vụ khi phù hợp |
| **Environment failure** | CI runner thiếu disk, DB down, Docker lỗi | Nhiều tests cùng fail; retry đơn lẻ lãng phí | Sửa readiness, resources, service availability |
| **External dependency outage** | Provider/collector/third-party API không reachable | Có thể hồi phục ngẫu nhiên | Dùng fake/local stub cho unit; integration policy riêng |
| **Non-hermetic test** | Dùng giờ, locale, random, file, shared DB | Rerun có input ẩn khác | Inject Clock/seed, per-test resources |
| **Incorrect test expectation** | Test assert thời điểm/format không được hợp đồng bảo đảm | Rerun chỉ đổi lịch và che assumption sai | Assert hành vi bất biến thay vì implementation details |
| **Real concurrency bug** | Chỉ fail dưới tải/song song | Rerun pass vẫn nguy hiểm | Tìm data race, lock/thread-safe code, regression stress |

**Điểm cần nhớ:** Một test thất bại một lần rồi pass khi rerun là **biểu hiện non-determinism**, nhưng không xác định ngay nó nằm ở test, hệ thống, hạ tầng hay kết quả quan sát. Cũng không được “xác nhận bug đã hết” chỉ vì chạy lại một lần đỗ.

### 2.1. Tại sao flakiness nguy hiểm dù tỷ lệ nhỏ?

Giả sử một test có xác suất fail độc lập mỗi lần là `p`. Nếu cho thêm một lần retry, xác suất nó vẫn fail cả hai lượt trong mô hình rất đơn giản là `p × p`; nhiều lỗi đầu tiên sẽ bị “che” khi lần hai đỗ. Nhưng trong CI thực tế, failure events thường **không độc lập**: DB đang down, Docker không đủ RAM, test state bị bẩn và network outage có thể kéo dài cả hai lượt. Công thức là một ví dụ tư duy, **không phải phương pháp dự đoán kết quả production**.

Điều đáng đo không chỉ là build cuối cùng xanh hay đỏ, mà là **first-attempt failure rate**, **pass-on-retry count**, số retry attempts, tần suất lỗi theo test/branch/runner và thời gian kỹ thuật dùng để xử lý.

### 2.2. Từ test failure đến quyết định xử lý

```text
JUnit execution FAILED
        |
        +--> Failure deterministic? --yes--> sửa code/test assertion
        |
        +--> Nhiều tests fail cùng hạ tầng?
        |          |
        |          +--yes--> sửa runner, DB, Docker, secrets, readiness
        |
        +--> Cho phép tối đa một retry để lấy thêm bằng chứng?
                   |
                   +--> retry PASS
                   |      |
                   |      +--> đánh dấu flaky, thu thập first failure
                   |      +--> assign owner + issue, tìm root cause
                   |      +--> build vẫn FAIL theo CI policy nghiêm
                   |
                   +--> retry FAIL
                          |
                          +--> lỗi còn tồn tại, sửa trực tiếp
                          +--> không retry vô hạn
```

Có thể xây pipeline “chấp nhận xanh nếu retry pass” trong một giai đoạn chuyển tiếp, nhưng điều đó phải là **ngoại lệ có kiểm soát**, có metrics và hạn xử lý, chứ không phải mặc định khiến team không thấy failures.

## 3. Phân biệt bốn cơ chế thường bị gọi chung là “retry”

| Cơ chế | Nó thực sự làm gì? | Phạm vi | Có chọn chỉ test thất bại? |
|---|---|---|---|
| Gradle Test Retry Plugin | Chạy lại những tests đã fail trong **cùng Gradle Test task** | Cấp test execution, per task | Có, tùy khả năng framework và filter |
| JUnit Jupiter `@RepeatedTest(n)` | Chạy method **n lần theo kế hoạch** | Cấp JUnit test invocation | **Không**; không đợi fail mới retry |
| Gradle `--rerun-tasks` | Buộc tasks thực thi lại dù up-to-date/cache | Cấp Gradle task graph | **Không**; không chỉ retry test fail |
| CI “rerun failed job” | Thực thi lại job/process pipeline | Cấp CI job; có thể đổi máy/state | Không tự chọn JUnit failing method |
| `./gradlew test --tests "Class.method"` | Chọn một method/class theo tên để chạy | Gradle Test filter | Không tự tự động retry; là lệnh chạy thủ công |
| HTTP/client retry | Thử lại một operation nghiệp vụ/network | Cấp application | Không phải JUnit/Gradle retry |

**Không nhầm `@RepeatedTest(20)` với cơ chế “chạy lại chỉ khi test fail”.** Nó có thể dùng làm diagnostic stress với một phép kiểm thử độc lập, nhưng không tự quản lý pass-on-retry hay root-cause tracking. Trong project runnable, `@RepeatedTest(5)` được đặt trong **diagnostic lane riêng**, không thêm ngẫu nhiên 5 lần thực thi vào PR unit suite.

### 3.1. Retry trong JUnit Extension khác Gradle retry

Có thể gặp JUnit extensions do team hoặc cộng đồng viết để chạy lại method khi fail. Cần xác minh compatibility/lifecycle, nhất là với `@BeforeEach`, `@AfterEach`, Spring TestContext, `@Transactional`, `@ParameterizedTest` và retry reporting. Ví dụ ở đây **không cài thêm retry extension trong JUnit**; chỉ dùng plugin Gradle để duy trì một nơi cấu hình attempts và báo cáo.

Đừng vừa bật retry extension trong JUnit, vừa bật Gradle Test Retry, vừa bật CI job reruns mà không tính số attempts tối đa. Khi mỗi tầng có retry, tổng thực thi có thể tăng rất nhiều và che incident kéo dài.

## 4. Gradle Test Retry Plugin làm việc như thế nào?

Plugin chính thức có ID:

```groovy
plugins {
    id 'org.gradle.test-retry' version '1.6.6'
}
```

Khi được áp dụng, plugin thêm cấu hình `retry` vào các Gradle `Test` tasks. **Chỉ apply plugin chưa bật retry**: `maxRetries` mặc định là 0. Bạn phải đặt chính sách trên task cần dùng.

Theo tài liệu plugin, sau khi một lượt chạy tất cả selected tests, plugin chạy lại những tests thất bại, lặp tiếp nếu còn lỗi và chưa hết số retry cho phép. Không phải cả suite luôn được chạy lại từ đầu. Với một số framework, dependencies/parameterization khiến phạm vi cần chạy lại rộng hơn một invocation.

### 4.1. Các tùy chọn then chốt

```groovy
tasks.named('test', Test) {
    retry {
        maxRetries = 1
        maxFailures = 10
        failOnPassedAfterRetry = true
        failOnSkippedAfterRetry = true
    }
}
```

| Thuộc tính | Ý nghĩa | Gợi ý |
|---|---|---|
| `maxRetries` | Số **lần retry sau lần chạy đầu** đối với một failed test | `1` nghĩa tối đa 2 attempts; `0` tắt |
| `maxFailures` | Ngưỡng số test failures trong **một retry round** mà tại ngưỡng trở lên plugin không tiếp tục retry | Tránh “retry storm” khi DB/runner chết |
| `failOnPassedAfterRetry` | Nếu đã fail lần đầu nhưng pass sau retry, có làm Gradle task fail? | `true` cho CI strict để nhìn thấy flakiness |
| `failOnSkippedAfterRetry` | Nếu test đã fail rồi bị skipped trong retry, có làm task fail? | `true` để không biến skip thành success |
| `filter` | Chọn tests **được phép retry**, dựa trên reported class name/annotations | Hạn chế retry cho integration nhóm đã duyệt |
| `classRetry` | Tùy chọn chạy lại toàn class với một số test classes có dependency/order | Chỉ dùng khi thật sự cần; tăng chi phí |

**Giá trị mặc định cần biết:** `maxRetries=0` nghĩa là không retry; `failOnPassedAfterRetry=false` theo plugin default nên pass-on-retry có thể làm task xanh; `failOnSkippedAfterRetry=true` theo plugin compatibility policy. Bài này **chủ động đặt true** cho hai cờ fail để phản ánh cách quản trị lỗi nghiêm ngặt.

`maxFailures=10` trong ví dụ là **ngưỡng minh họa**, không phải best-practice universal. Nếu có 10 failed tests trong một round và threshold là 10, retry bị ngừng; nếu số failure nhỏ hơn ngưỡng và còn attempts, nó có thể tiếp tục. Theo tài liệu plugin, ngưỡng được áp dụng **mỗi round**, không đơn giản cộng dồn qua cả suite.

### 4.2. Một trường hợp cụ thể

Giả sử Gradle task có 40 tests:
1. Lượt đầu: 38 pass, `A` fail, `B` fail.
2. `maxRetries=1`: plugin chọn các tests fail (hoặc method/class scope mà framework hỗ trợ) để thử lại.
3. Lượt retry: `A` pass, `B` fail.
4. `B` còn fail → task fail.
5. Nếu cả `A` và `B` đều pass nhưng `failOnPassedAfterRetry=true`, **task vẫn fail** vì đã phát hiện flaky.

**Đừng giải thích “lượt 2 xanh nên build chuẩn”.** Lần thử lại chỉ thêm bằng chứng rằng lần đầu không ổn định. CI sẽ cần ghi failure ban đầu và assign root-cause owner.

### 4.3. Parameterized tests và phạm vi retry

Với JUnit Jupiter `@ParameterizedTest`, plugin có thể **retry toàn bộ method với tất cả arguments**, kể cả những invocations đã pass ở lượt đầu, do giới hạn selection granularity của framework. Vì vậy:
- Không giả định một parameter invocation duy nhất được retry.
- Không thực hiện side effects không idempotent trong parameterized tests.
- Gắn parameter index/arguments hữu ích vào tên test báo cáo, nhưng tránh random/dynamic names gây report merge khó.
- Nếu parameterized method chứa 200 cases, một retry có thể tốn đáng kể; chia nhóm test hoặc tối ưu fixture khi phù hợp.

### 4.4. Filter retry khác filter test selection

```groovy
tasks.named('test', Test) {
    retry {
        maxRetries = 1
        filter {
            includeClasses.add('*IntegrationTest')
            excludeClasses.add('*PaymentContractTest')
        }
    }
}
```

Đây là **đoạn cấu hình thay thế để minh họa**, không nằm trong build chạy ở phần 7. `filter` ở đây quyết định **test nào được phép retry sau khi fail**, chứ **không** quyết định test nào được chạy lần đầu. Gradle `--tests`/JUnit `includeTags` là lớp test selection khác.

Nếu tên class không match retry filter, test đó vẫn chạy bình thường nhưng khi fail không được plugin retry. Filtering theo class annotations phụ thuộc annotation trên **class**, không phải tùy tiện theo `@Tag` của một method; đừng coi hai filter systems là đồng nhất.

### 4.5. Những gì plugin không làm

- Không sửa bug/fixture race.
- Không giữ transaction hoặc Spring context từ lần đầu để bạn assert trạng thái.
- Không chuyển mọi test thành idempotent.
- Không retry test bị CI bỏ qua do Gradle tags/filter.
- Không phục hồi database/outbox/Redis key bị thay đổi không rollback ở lần đầu.
- Không bảo đảm một external API sẽ có lại trước retry.
- Không chứng minh test đúng nếu suite được skip/up-to-date.
- Không tạo test ownership, quarantine expiry hay dashboard triage tự động.

**Do đó, retry cần được coi là dữ liệu điều tra và giảm nhiễu có kiểm soát, không phải “phép màu xanh pipeline”.**

## 5. Xây chính sách CI không che giấu lỗi

Một policy điển hình cho dự án muốn nâng độ tin cậy:

| Nhóm | Local developer | Pull request CI | Nightly/diagnostic |
|---|---|---|---|
| Pure unit | Không retry mặc định | Tối đa 1 retry để phát hiện; pass-on-retry vẫn fail task | `@RepeatedTest`/stress test chọn lọc |
| Spring slice | Không retry hoặc opt-in | Cùng policy strict nếu test đã phân loại an toàn | Phân tích context cache/mock state |
| Integration với DB/containers | Test environment riêng | Một retry giới hạn, readiness checks trước test | Multi-run, resource isolation |
| External contract | Stub/unit nội bộ; không cần cloud | Chỉ chạy trong job có dependency rõ ràng | Retry theo external test agreement |
| Known flaky đã cách ly | Không nằm trong PR gate chính | Không âm thầm xóa khỏi coverage | Chạy dedicated quarantine lane + issue owner |
| Smoke post-deploy | Không phải unit test | Không tự “skip” lỗi production | Bounded wait/retry health checks theo readiness policy |

**Cách chọn failOnPassedAfterRetry:**
- `true` phù hợp khi chất lượng tín hiệu quan trọng và team cam kết xử lý flakiness. Build đỏ nhắc rằng first attempt đã lỗi.
- `false` có thể được chọn **tạm thời** để tránh block mọi PR của một legacy suite rất flaky; nhưng phải có dashboard/alert về flaky failures, issue tracking và ngưỡng cho phép. Nếu tắt cảnh báo, độ tin cậy sẽ xấu dần.
- Không dùng `ignoreFailures=true` để “sửa pipeline”. Khi bỏ qua failures, cơ chế fail-on-retry không còn bảo vệ contract như mong đợi.

### 5.1. Vì sao maxRetries thường nhỏ?

Một hoặc hai retry đã đủ cung cấp tín hiệu “có thể non-deterministic”. Cho 5–10 retries làm:
- Tăng chi phí CI và thời gian feedback.
- Tăng khả năng một bug có xác suất nhỏ bị che.
- Làm database/container state bị thử lại nhiều lần, khó truy dấu.
- Che dependency outage thay vì fail nhanh với diagnostic rõ ràng.

Nếu một operation network **trong ứng dụng** có chính sách retry riêng, hãy test chính retry đó với controlled fake clock/fault injection; không tăng JUnit retries để thay thế hành vi production.

### 5.2. Không khởi động lại toàn bộ job để “sửa” một assertion

CI rerun job có thể chạy trên worker mới, với caches, database snapshot, Docker state và load khác. Việc nó pass chỉ cho biết **một execution khác** thành công; nó không xác định bước nào của build trước fail hoặc có bao nhiêu test retries đã xảy ra. Hãy giữ logs, JUnit XML và CI environment metadata từ **lần đầu** trước khi cho rerun.

## 6. Reporting: pass-on-retry phải còn dấu vết

Gradle có HTML/XML reports cho mỗi `Test` task:
- `build/reports/tests/test/index.html`.
- `build/test-results/test/`.

Gradle Test Retry Plugin báo cáo mỗi execution như một sự kiện. Với một số CI servers, một fail-then-pass có thể được tính/hiển thị khác nhau tùy XML parser. Gradle hỗ trợ `reports.junitXml.mergeReruns`.

### 6.1. mergeReruns và mục tiêu của reporting

```groovy
tasks.named('test', Test) {
    reports {
        junitXml {
            outputPerTestCase = true
            mergeReruns = false
        }
    }
}
```

Trong project mẫu đặt `mergeReruns=false` để XML có các test executions riêng, dễ đối chiếu failure đầu. Với `mergeReruns=true`, Gradle có thể gộp fail→pass cùng test case và biểu diễn lỗi ban đầu bằng `<flakyFailure>` thay cho `<failure>`. Điều này giúp một số CI parser không làm đỏ report khi cuối cùng test đã pass, **nhưng có nguy cơ một dashboard bỏ qua phần flakyFailure**.

**Rất quan trọng:** `mergeReruns` chỉ thay đổi cách **ghi XML**, **không** kích hoạt retry. Việc retry đến từ plugin hoặc test framework. Nếu CI đọc XML và tự quyết định build status, cần bảo đảm nó không áp policy trái ngược `failOnPassedAfterRetry`.

### 6.2. Đọc số liệu cho đúng

| Trạng thái | Diễn giải |
|---|---|
| `PASS` first attempt | Test xanh bình thường |
| `FAIL` rồi `PASS` | Flaky signal; không xóa failure đầu |
| `FAIL` cả hai attempts | Lỗi còn tồn tại; không tự chứng minh deterministic |
| `SKIPPED` trên retry | Phải review vì test đã fail nhưng bị skip |
| Task `UP-TO-DATE` | Không execute lại trong build lần này |
| Task `FROM-CACHE` | Kết quả lấy từ cache; không phải execution mới |
| Task `NO-SOURCE`/không selected tests | Không có bằng chứng đã chạy test |
| Build xanh do `ignoreFailures` | Tín hiệu gate sai: có thể vẫn có JUnit failures |

Khi gửi báo cáo CI, ít nhất nên có: first-attempt failures, pass-on-retry tests, permanently failed tests, skipped tests, retries consumed, build/task status và environment fingerprint. Không chỉ gửi một emoji xanh kèm tổng tests.

## 7. Dự án hoàn chỉnh Spring Boot 3.5.8, Java 17+, Gradle

Project này cố ý không có external DB, HTTP server, Redis hoặc exporter để tập trung vào **flakiness và retry policy**. Nó có:
- Service tính giá dùng `Clock` inject để kiểm thử ngày tháng deterministic.
- Async service dùng `CompletableFuture` và executor do test quản lý; test chờ bằng timeout, không ngủ đoán.
- File writer dùng `@TempDir` để không va chạm khi nhiều forks/test methods.
- Một `@SpringBootTest` nhẹ để kiểm chứng DI mà không phụ thuộc external services.
- `@RepeatedTest(5)` nằm trong **diagnostic** group riêng để phân biệt repeated execution với retry-on-failure.
- Gradle Test Retry Plugin bật tối đa **một retry trên CI**, và cấu hình **failOnPassedAfterRetry=true**.

### 7.1. Cây file

```text
settings.gradle
build.gradle
src/main/java/com/example/retrylab/
    RetryLabApplication.java
    TimeConfiguration.java
    CheckoutQuote.java
    CheckoutService.java
    AsyncReceiptService.java
    ReceiptFileWriter.java
src/test/java/com/example/retrylab/
    CheckoutServiceTest.java
    AsyncReceiptServiceTest.java
    ReceiptFileWriterTest.java
    CheckoutSpringTest.java
    StabilityRepetitionTest.java
```

Không có `src/test/resources/application.properties` bắt buộc; app không có DB/web. Demo không có “flaky-by-design” trong normal test lane. Nếu muốn kiểm thử thật retry plugin bằng deliberate failure, chỉ làm trên branch/job diagnostic riêng, không đưa test có random failure vào main suite.

### 7.2. settings.gradle

```groovy
rootProject.name = 'spring-boot-retry-lab'
```

### 7.3. build.gradle đầy đủ

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
    id 'org.gradle.test-retry' version '1.6.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

def onCi = System.getenv().containsKey('CI')

tasks.named('test', Test) {
    useJUnitPlatform {
        // Quarantine và diagnostic không nằm trong PR test gate.
        excludeTags 'quarantine', 'diagnostic'
    }

    // Một JVM để giữ ví dụ dễ tái hiện; tăng dần sau khi
    // kiểm chứng isolation của các Spring/IO tests.
    maxParallelForks = 1

    retry {
        // Local: không retry. CI: initial attempt + 1 retry.
        maxRetries = onCi ? 1 : 0
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

    testLogging {
        events 'failed', 'skipped'
        exceptionFormat 'full'
    }
}

// Test chạy lặp lại để điều tra tính ổn định.
// KHÔNG phải retry-on-failure.
tasks.register('diagnosticTest', Test) {
    description = 'Run repeated diagnostic tests'
    group = 'verification'

    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform {
        includeTags 'diagnostic'
    }

    maxParallelForks = 1

    retry {
        maxRetries = 0
    }
}

// Lane cho known flaky tests nếu sau này cần cách ly.
// Project mẫu ban đầu KHÔNG có test nào mang tag này.
tasks.register('quarantineTest', Test) {
    description = 'Run quarantined tests separately'
    group = 'verification'

    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform {
        includeTags 'quarantine'
    }

    maxParallelForks = 1

    retry {
        maxRetries = 0
    }
}

// check của Java plugin đã phụ thuộc vào test.
// Hai task diagnostic/quarantine không được thêm vào check.
```

**Tính chất của cấu hình này:**
- `CI` được nhận diện bởi sự **hiện diện** của biến môi trường, không phải giá trị chuỗi `"true"`. CI provider phải set nó nhất quán; nếu không có, retry tắt.
- `maxRetries=1` nghĩa là initial execution + tối đa một lần retry cho test fail. Không phải chạy mọi test hai lần.
- `failOnPassedAfterRetry=true` làm một fail→pass vẫn khiến Gradle `test` đỏ trên CI.
- `maxFailures=10` giới hạn retry storm; ngưỡng chỉ là ví dụ.
- `reports.junitXml.mergeReruns=false` để giữ dữ liệu executions riêng trong XML; `outputPerTestCase=true` giúp log gắn với test method.
- `diagnosticTest` chọn `@Tag("diagnostic")`, không có plugin retries, để phân biệt JUnit repetition.
- `quarantineTest` chọn `@Tag("quarantine")`; ban đầu không chọn test nào vì project không chứa flaky cases cố ý.
- `./gradlew check` chạy `test`, **không tự chạy** `diagnosticTest` hay `quarantineTest`.
- `maxParallelForks=1` và no external service giúp diagnosis dễ trước khi thử tăng concurrency.

**Không set `ignoreFailures=true` hoặc `failFast=true` trong ví dụ**. `ignoreFailures=true` làm task không chặn build đúng; `failFast=true` có thể dừng sớm và làm mất thông tin về các failure khác trong cùng run. Sau khi triage policy ổn định, team có thể quyết định fail-fast cho một nhóm test riêng theo mục tiêu feedback.

### 7.4. Main application

Tệp `src/main/java/com/example/retrylab/RetryLabApplication.java`:

```java
package com.example.retrylab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RetryLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(RetryLabApplication.class, args);
    }
}
```

Không có `starter-web`, nên khởi động Spring context không mở HTTP port. Không có `starter-data-jpa`, nên cũng không tự mở DB connections. Mục tiêu chỉ là kiểm tra DI và business test patterns.

### 7.5. Inject Clock: loại bỏ phụ thuộc ngày giờ hệ thống

Tệp `src/main/java/com/example/retrylab/TimeConfiguration.java`:

```java
package com.example.retrylab;

import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

Tệp `src/main/java/com/example/retrylab/CheckoutQuote.java`:

```java
package com.example.retrylab;

import java.math.BigDecimal;
import java.time.LocalDate;

public record CheckoutQuote(
        String orderCode,
        BigDecimal payable,
        LocalDate processedDate) {
}
```

Production clock được Spring inject, còn unit test truyền `Clock.fixed(...)` trực tiếp. Cách này giúp test kiểm tra ngày mong đợi **không phụ thuộc nửa đêm, timezone của máy CI hoặc daylight-saving**.

### 7.6. CheckoutService.java

Tệp `src/main/java/com/example/retrylab/CheckoutService.java`:

```java
package com.example.retrylab;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.time.LocalDate;
import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final Clock clock;

    public CheckoutService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public CheckoutQuote quote(
            String orderCode,
            BigDecimal subtotal,
            int discountPercent) {

        if (orderCode == null || orderCode.isBlank()) {
            throw new IllegalArgumentException(
                    "orderCode must not be blank");
        }

        Objects.requireNonNull(subtotal, "subtotal");

        if (subtotal.signum() < 0) {
            throw new IllegalArgumentException(
                    "subtotal must not be negative");
        }

        if (discountPercent < 0 || discountPercent > 100) {
            throw new IllegalArgumentException(
                    "discountPercent must be in 0..100");
        }

        BigDecimal payable = subtotal.multiply(
                BigDecimal.valueOf(100 - discountPercent))
            .divide(
                BigDecimal.valueOf(100),
                2,
                RoundingMode.HALF_UP);

        return new CheckoutQuote(
                orderCode,
                payable,
                LocalDate.now(clock));
    }
}
```

Đây là stateless Spring `@Service`: mỗi lần `quote(...)` dùng input và `Clock`; không có mutable cache/static counter hay current-date global. Unit test sẽ dùng fixed Clock, integration test chỉ assert nghiệp vụ amount và bean wiring để tránh assertion về thời gian máy.

### 7.7. AsyncReceiptService.java

Tệp `src/main/java/com/example/retrylab/AsyncReceiptService.java`:

```java
package com.example.retrylab;

import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

public final class AsyncReceiptService {

    private final Executor executor;

    public AsyncReceiptService(Executor executor) {
        this.executor = Objects.requireNonNull(executor);
    }

    public CompletableFuture<String> normalizeAsync(
            String code) {
        return CompletableFuture.supplyAsync(() -> {
            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException(
                        "code must not be blank");
            }
            return code.trim().toUpperCase(Locale.ROOT);
        }, executor);
    }
}
```

Async service không tạo một global executor tự sống mãi; test cung cấp executor của riêng mình. `CompletableFuture` cho phép test **chờ một kết quả có timeout**, thay vì `Thread.sleep(50)` rồi đoán worker đã hoàn tất.

Trong production Spring Boot, `@Async` thường dùng `TaskExecutor` do Spring quản lý. Nguyên tắc vẫn tương tự: inject/expose một completion signal hoặc quan sát durable state theo deadline. Việc sleep trong test làm nhiều lỗi chỉ xuất hiện khi CI CPU chậm hoặc background scheduler bị chặn.

### 7.8. ReceiptFileWriter.java

Tệp `src/main/java/com/example/retrylab/ReceiptFileWriter.java`:

```java
package com.example.retrylab;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

public final class ReceiptFileWriter {

    public Path write(
            Path directory,
            String baseName,
            String contents) throws IOException {

        Objects.requireNonNull(directory);
        Objects.requireNonNull(baseName);
        Objects.requireNonNull(contents);

        Files.createDirectories(directory);

        Path output = directory.resolve(
                baseName + ".txt");

        Files.writeString(
                output,
                contents,
                StandardCharsets.UTF_8);

        return output;
    }
}
```

Test nhận một directory riêng qua `@TempDir`, không ghi vào `build/receipt.txt` cố định. Khi tăng Gradle `maxParallelForks` hoặc bật JUnit concurrent, per-test directory giảm nguy cơ xung đột file. Trong code production thật, validate `baseName` để chống path traversal nếu lấy từ input không tin cậy; ví dụ đào tạo chỉ gọi nó bằng hằng test an toàn.

## 8. Các JUnit tests ổn định: không “giả flaky” bằng random

### 8.1. CheckoutServiceTest.java: logic và fixed clock

Tệp `src/test/java/com/example/retrylab/CheckoutServiceTest.java`:

```java
package com.example.retrylab;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class CheckoutServiceTest {

    private final Clock fixedClock = Clock.fixed(
            Instant.parse("2026-01-20T23:59:59Z"),
            ZoneOffset.UTC);

    private final CheckoutService service =
            new CheckoutService(fixedClock);

    @Test
    void fixedClockMakesProcessedDateStable() {
        CheckoutQuote quote = service.quote(
                "ORD-A",
                new BigDecimal("100.00"), 10);

        assertThat(quote.processedDate())
            .isEqualTo(LocalDate.of(2026, 1, 20));
        assertThat(quote.payable())
            .isEqualByComparingTo("90.00");
    }

    @Test
    void roundingIsDeterministic() {
        CheckoutQuote quote = service.quote(
                "ORD-B",
                new BigDecimal("99.99"), 25);

        assertThat(quote.payable())
            .isEqualByComparingTo("74.99");
    }

    @Test
    void invalidDiscountAlwaysThrows() {
        assertThatThrownBy(() ->
                service.quote("ORD-C",
                    new BigDecimal("10.00"), 101))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessage(
                "discountPercent must be in 0..100");
    }

    @Test
    void separateInputsDoNotShareMutableState() {
        CheckoutQuote first = service.quote(
                "ORD-D", new BigDecimal("10"), 0);
        CheckoutQuote second = service.quote(
                "ORD-E", new BigDecimal("20"), 50);

        assertThat(first.orderCode()).isEqualTo("ORD-D");
        assertThat(first.payable())
            .isEqualByComparingTo("10.00");

        assertThat(second.orderCode()).isEqualTo("ORD-E");
        assertThat(second.payable())
            .isEqualByComparingTo("10.00");
    }
}
```

Có **4 ca `@Test`**. Test đầu dùng fixed UTC time; nếu CI chạy gần nửa đêm hoặc ở timezone khác, kết quả ngày vẫn như nhau. Tests khác assert BigDecimal bằng `isEqualByComparingTo` thay vì format string của hệ thống.

**Không dùng `LocalDate.now()` trực tiếp trong assertion** để kiểm chứng code đã gọi `LocalDate.now()` một lần trước đó: ngày có thể đổi giữa hai calls tại ranh giới nửa đêm.

### 8.2. AsyncReceiptServiceTest.java: chờ tương lai bằng deadline

Tệp `src/test/java/com/example/retrylab/AsyncReceiptServiceTest.java`:

```java
package com.example.retrylab;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class AsyncReceiptServiceTest {

    @Test
    void asyncResultIsWaitedForRatherThanSleptFor()
            throws Exception {

        ExecutorService pool =
                Executors.newSingleThreadExecutor();

        try {
            AsyncReceiptService service =
                    new AsyncReceiptService(pool);

            CompletableFuture<String> future =
                    service.normalizeAsync(" inv-101 ");

            assertThat(future.get(3, TimeUnit.SECONDS))
                .isEqualTo("INV-101");
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void rejectedInputIsVisibleAsFutureFailure()
            throws Exception {

        ExecutorService pool =
                Executors.newSingleThreadExecutor();

        try {
            AsyncReceiptService service =
                    new AsyncReceiptService(pool);

            CompletableFuture<String> future =
                    service.normalizeAsync("   ");

            assertThatThrownBy(
                () -> future.get(3, TimeUnit.SECONDS))
                .isInstanceOf(ExecutionException.class)
                .hasCauseInstanceOf(
                    IllegalArgumentException.class);
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void independentFutureResultsDoNotShareState()
            throws Exception {

        ExecutorService pool =
                Executors.newFixedThreadPool(2);

        try {
            AsyncReceiptService service =
                    new AsyncReceiptService(pool);

            CompletableFuture<String> a =
                    service.normalizeAsync("a-1");
            CompletableFuture<String> b =
                    service.normalizeAsync("b-2");

            assertThat(a.get(3, TimeUnit.SECONDS))
                .isEqualTo("A-1");
            assertThat(b.get(3, TimeUnit.SECONDS))
                .isEqualTo("B-2");
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Có **3 ca `@Test`**. `Future.get(timeout)` là hợp đồng chờ completion thực sự; timeout chỉ là giới hạn để không treo CI vô hạn. `shutdownNow()` trong `finally` đảm bảo executor không còn được bỏ mặc sau khi test fail. Không assert chính xác thread name/timing vì scheduler không bảo đảm thứ tự đó.

### 8.3. ReceiptFileWriterTest.java: @TempDir thay vì file dùng chung

Tệp `src/test/java/com/example/retrylab/ReceiptFileWriterTest.java`:

```java
package com.example.retrylab;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.assertj.core.api.Assertions.assertThat;

class ReceiptFileWriterTest {

    private final ReceiptFileWriter writer =
            new ReceiptFileWriter();

    @Test
    void writesReceiptIntoPerTestDirectory(
            @TempDir Path directory) throws IOException {

        Path file = writer.write(
                directory, "receipt", "paid");

        assertThat(Files.exists(file)).isTrue();
        assertThat(Files.readString(
                file, StandardCharsets.UTF_8))
            .isEqualTo("paid");
    }

    @Test
    void anotherMethodMayUseSameFileNameSafely(
            @TempDir Path directory) throws IOException {

        Path file = writer.write(
                directory, "receipt", "refunded");

        assertThat(Files.readString(
                file, StandardCharsets.UTF_8))
            .isEqualTo("refunded");
    }
}
```

Có **2 ca `@Test`**. Dù cùng dùng filename `receipt.txt`, mỗi test method nhận thư mục `@TempDir` riêng do JUnit quản lý. Đây là kiểu isolation mạnh hơn `@ResourceLock("receipt.txt")` nếu Gradle được phép fork nhiều JVM vì resource lock chỉ phối hợp trong một JUnit execution plan.

### 8.4. CheckoutSpringTest.java: context thật, không bám đồng hồ

Tệp `src/test/java/com/example/retrylab/CheckoutSpringTest.java`:

```java
package com.example.retrylab;

import java.math.BigDecimal;
import java.time.Clock;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class CheckoutSpringTest {

    @Autowired
    CheckoutService service;

    @Autowired
    Clock clock;

    @Test
    void contextWiresServiceAndClock() {
        assertThat(service).isNotNull();
        assertThat(clock).isNotNull();
    }

    @Test
    void quoteWorksInSpringContext() {
        CheckoutQuote quote = service.quote(
                "SPRING-A", new BigDecimal("100"), 20);

        assertThat(quote.orderCode())
            .isEqualTo("SPRING-A");

        assertThat(quote.payable())
            .isEqualByComparingTo("80.00");

        // Không assert processedDate == LocalDate.now()
        // vì test này kiểm tra wiring/giá, không phải Clock.
    }
}
```

Có **2 ca `@Test`**. Test khởi tạo ApplicationContext và bean thật, không kết nối DB/web/external services. Spring Boot có thể cache cùng context giữa tests; vì beans trong demo stateless, không reset mock/shared state.

### 8.5. StabilityRepetitionTest.java: @RepeatedTest là stress/diagnostic

Tệp `src/test/java/com/example/retrylab/StabilityRepetitionTest.java`:

```java
package com.example.retrylab;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.RepeatedTest;
import org.junit.jupiter.api.RepetitionInfo;
import org.junit.jupiter.api.Tag;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("diagnostic")
class StabilityRepetitionTest {

    @RepeatedTest(5)
    void identicalInputHasIdenticalOutcome(
            RepetitionInfo repetitionInfo) {

        CheckoutService service = new CheckoutService(
                Clock.fixed(
                    Instant.parse("2026-01-20T00:00:00Z"),
                    ZoneOffset.UTC));

        CheckoutQuote result = service.quote(
                "REPEAT-A",
                new BigDecimal("100.00"), 10);

        assertThat(result.payable())
            .isEqualByComparingTo("90.00");

        assertThat(repetitionInfo.getCurrentRepetition())
            .isBetween(1, 5);

        assertThat(repetitionInfo.getTotalRepetitions())
            .isEqualTo(5);
    }
}
```

Lớp này có **một `@RepeatedTest(5)` source method**, tạo **5 invocations** khi chạy `diagnosticTest`. Nó không đợi method fail mới chạy lại; cũng không chẩn đoán được race nếu code không có tình huống race. Mục đích là minh họa phương thức lặp có deadline/inputs cố định và so sánh với plugin retry-on-failure.

**Đếm test trong sample:** 4 + 3 + 2 + 2 = **11 ca `@Test`** trong task `test`, và 5 invocations từ `@RepeatedTest` khi chạy `diagnosticTest`. Vì không có intentionally failing test, khi toàn bộ suite pass ở first attempt, **không có retry thực tế nào được kích hoạt**. Để xác minh plugin trên một lỗi có kiểm soát, dùng một branch chuyên diagnostic hoặc project fixture riêng, không chèn random failing test vào branch chính.

## 9. Phân tích anti-pattern: Thread.sleep và test bất đồng bộ

Một cách viết không ổn định:

```java
CompletableFuture<String> future =
        service.normalizeAsync("INV-22");

Thread.sleep(20); // Hy vọng worker hoàn thành
assertThat(future.isDone()).isTrue();
```

Đây là **fragment sai được đưa ra để phân tích**, không phải test runnable trong project. Nó phụ thuộc CPU scheduler, thread pool backlog, GC pauses và CI host. `Thread.sleep(20)` không đưa ra contract rằng worker chắc đã hoàn tất.

Cách sửa:

```java
CompletableFuture<String> future =
        service.normalizeAsync("INV-22");

assertThat(future.get(3, TimeUnit.SECONDS))
    .isEqualTo("INV-22");
```

Đây là fragment trong method có `service` và `TimeUnit`. Nó chờ đúng outcome thực, tối đa ba giây. Nếu app không expose `Future`, dùng `CountDownLatch`, `CompletableFuture`, Awaitility với polling deadline, hoặc trạng thái durable có thể quan sát. Không chỉ tăng `Thread.sleep(20)` lên 5000 để “ổn định”.

### 9.1. Latch phải gắn với một sự kiện thật

```java
CountDownLatch finished = new CountDownLatch(1);

executor.submit(() -> {
    try {
        performWork();
    } finally {
        finished.countDown();
    }
});

assertThat(finished.await(3, TimeUnit.SECONDS))
    .isTrue();
```

Đây là fragment minh họa có `executor` và `performWork()` được khai báo. `countDown()` trong finally bảo đảm test không treo nếu worker ném exception, **nhưng** vẫn cần capture/report exception (ví dụ qua `Future.get`) để không chuyển lỗi worker thành test “xanh” giả. Latch chỉ nói worker đến điểm countDown, không tự chứng minh kết quả business chính xác.

### 9.2. Awaitility (khi thật sự test eventual consistency)

Với Kafka consumer, scheduler hoặc eventual DB state, có thể dùng Awaitility và một condition có timeout:

```java
await().atMost(Duration.ofSeconds(5))
       .untilAsserted(() ->
           assertThat(repository.existsById(id)).isTrue());
```

Đây là **fragment tùy chọn**, cần dependency `org.awaitility:awaitility`, imports và một repository được định nghĩa. Nó **không thuộc build mẫu**. Dùng polling với deadline và thông điệp lỗi rõ; không retry vô hạn. Cũng phải bảo đảm test poll trên state đã committed/visible, không chỉ một EntityManager cache cũ.

## 10. Test flakiness do ngày giờ, timezone và dữ liệu ngẫu nhiên

### 10.1. Đồng hồ hệ thống

Sai:

```java
LocalDate expected = LocalDate.now();
// ... service làm việc ...
assertThat(result.date()).isEqualTo(expected);
```

Nếu đổi ngày ở giữa hai lệnh (đặc biệt gần midnight hoặc DST), assertion có thể fail. Dùng `Clock` được inject với `Clock.fixed` trong unit tests. Nếu phải test timezone, dùng `Clock.fixed(instant, ZoneId.of("Asia/Ho_Chi_Minh"))` và expected `LocalDate` cụ thể, không đổi timezone global của JVM trong concurrent tests.

### 10.2. Random seeds

Một test sinh 1.000 records bằng `new Random()` nhưng không log seed sẽ khó tái hiện lỗi. Dùng seed cố định:

```java
Random random = new Random(20261108L);
int value = random.nextInt(100);
assertThat(value).isBetween(0, 99);
```

Đây là fragment. Nếu property-based test muốn seed ngẫu nhiên để khám phá nhiều input, hãy **ghi lại seed và shrinkable counterexample** khi fail để replay chính xác; không lấy lý do random để chấp nhận mọi failed test là flaky.

### 10.3. UUID và unique test data

Một `UUID.randomUUID()` là cách tốt để tránh collision giữa test records khi tạo identifiers, nhưng test không nên assert một UUID literal. Thay vào đó:
- Assert format/uniqueness theo contract.
- Có cleanup bằng test-generated namespace/ID.
- Nếu fail, log ID đã dùng để có thể truy vết.
- Không dựa vào thứ tự sinh IDs của nhiều threads.
- Trong DB tests, ưu tiên schema/database riêng khi integration tests có truncate-all.

Random IDs làm giảm va chạm, nhưng **không tạo transactional isolation** cho câu `DELETE FROM table` xóa toàn bộ dữ liệu.

## 11. JUnit parallel, Gradle forks và race conditions

Một suite có thể pass với `maxParallelForks=1` rồi fail khi tăng lên 4. Cần phân biệt:
- Gradle `maxParallelForks`: tối đa số **test JVM processes** song song cho một Test task.
- `--max-workers`: worker budget toàn Gradle build.
- JUnit Jupiter parallel config: threads/classes/methods bên trong từng JVM.
- `@ResourceLock`: phối hợp dùng tài nguyên trong cùng JUnit execution plan; **không khóa tài nguyên giữa hai JVM forks**.
- `@Isolated`: cô lập class trong cùng JUnit plan, **không** chặn Gradle forks khác.
- `@TempDir`: cấp path riêng, hữu ích cả giữa methods/JVMs.

Đừng gán việc “tăng parallel làm test đỏ” cho Gradle plugin rồi bật retry. Hãy đo worker ID/PID/thread, tìm state chung và sửa fixture.

### 11.1. Quan sát process và thread

```java
System.out.println(
    "gradleWorker="
        + System.getProperty("org.gradle.test.worker", "IDE")
        + " pid=" + ProcessHandle.current().pid()
        + " thread=" + Thread.currentThread().getName());
```

Đây là fragment diagnostic. `org.gradle.test.worker` phân biệt Gradle test worker **process**, không phải tên method/thread. Khi chạy IDE không delegate sang Gradle, property có thể không tồn tại. Không assert một worker ID cụ thể trong JUnit.

### 11.2. Khi nào @ResourceLock hợp lý?

```java
@Test
@ResourceLock(
    value = Resources.SYSTEM_PROPERTIES,
    mode = ResourceAccessMode.READ_WRITE)
void modifiesSystemProperties() {
    String original = System.getProperty("feature.flag");
    try {
        System.setProperty("feature.flag", "true");
        // assertion...
    } finally {
        if (original == null) {
            System.clearProperty("feature.flag");
        } else {
            System.setProperty("feature.flag", original);
        }
    }
}
```

Đây là fragment với imports JUnit cần thiết. Cả **lock** lẫn **finally restore** đều quan trọng. Một test khác không khai báo lock tương ứng có thể vẫn sửa system property, vì `@ResourceLock` chỉ phối hợp những nodes tuân theo lock manager của Jupiter.

Nếu tests ở hai Gradle JVMs cùng ghi `build/report.json`, `@ResourceLock("report")` trong mỗi JVM không giúp gì; cần per-worker path hoặc một external lock thật.

## 12. Spring Boot TestContext và những nguyên nhân flaky đặc thù

### 12.1. Spring ApplicationContext cache

Spring TestContext cache có thể reuse `ApplicationContext` giữa nhiều test classes trong cùng JVM nếu configuration key giống nhau. Việc này tốt cho performance nhưng nghĩa là:
- Singleton bean có mutable fields có thể bị tests khác làm bẩn.
- In-memory queue/cache/counter có thể chưa được reset.
- Một test gọi `@DirtiesContext` có thể đóng context khi test khác đang sử dụng nó, đặc biệt trong parallel execution.
- `@MockitoBean`/`@MockitoSpyBean` là bean overrides trong context; concurrent tests cùng stubbing/reset/verify mock có thể tạo race.

Spring Framework có hướng dẫn tránh parallel cho các tests dùng `@DirtiesContext`, mock bean overrides hoặc state/order dependencies không được cô lập.

**Sửa đúng:** tách serial lane, hạn chế context mutation, dùng stateless beans hoặc test-specific `@TestConfiguration`/fixtures; đừng đặt `@DirtiesContext` lên mọi test chỉ để “đảm bảo sạch” vì nó làm context startup lặp lại và che vấn đề state design.

### 12.2. @Transactional test rollback không bao phủ mọi thread

Một test:

```java
@SpringBootTest
@Transactional
class OrderTest {
    // ...
}
```

thường rollback **test-managed transaction** cuối method. Nhưng `@SpringBootTest(webEnvironment=RANDOM_PORT)` mở server trên thread khác; request handler có transaction riêng có thể **commit thật** dù test method rollback. Tương tự `@Async` worker và broker consumer không tự tham gia ThreadLocal transaction của test thread.

Khi test chạy song song, cùng một DB/schema có thể chứa rows mà một test tưởng đã rollback; test khác thấy chúng hoặc bị unique constraint collision.

**Sửa đúng:** chia data theo test ID/schema, cleanup rõ ràng, tránh shared truncate, kiểm tra commit thực và dùng Testcontainers DB engine tương ứng. Không tăng retry để che state leak.

### 12.3. @DataJpaTest và H2 khác production DB

`@DataJpaTest` thường dùng embedded database và test-managed transaction rollback theo cấu hình mặc định. Nó phù hợp persistence slice, nhưng không chứng minh PostgreSQL locking/deadlock/isolation. Nếu failure chỉ xảy ra trên CI với external DB, hãy tách integration test dùng production-like Testcontainers, fixture và transaction boundary rõ. **Đừng coi test retry PASS là bằng chứng SQL đã đúng.**

### 12.4. Spring event listener và commit timing

`@EventListener` thường nhận event đồng bộ ngay lúc publish; `@TransactionalEventListener(AFTER_COMMIT)` đợi commit của transaction chứa event. Một `@Transactional` test mặc định rollback có thể khiến listener AFTER_COMMIT **không chạy** mà không có lỗi gì.

Nếu test mong callback after commit chạy, cần một transaction commit thật ngoài test-managed transaction, hoặc `TestTransaction.flagForCommit()` + `end()` đúng lúc. Retry không thay đổi transaction phase semantics; một suite “lúc pass lúc fail” do test nhầm timing cần được sửa đúng ranh giới.

### 12.5. ApplicationContext startup / condition timing

Khi test cần external Config Server, database, Redis hoặc một mock HTTP server, các properties như port/URL phải được cung cấp **trước khi context refresh**. Sử dụng `@DynamicPropertySource` và random ports từ Testcontainers/MockWebServer thay cho một fixed port. Nếu dependency chưa ready, dùng supported startup wait/readiness strategy, không `Thread.sleep(3000)`.

Nếu context fail do property sai hoặc `@ConditionalOnBean` không match, lỗi đó có thể deterministic; việc “rerun CI” không sửa bean configuration.

## 13. Testcontainers và external services: retry có thể làm xấu tình hình

Một IntegrationTest dùng PostgreSQL Testcontainers có thể fail vì:
- Docker daemon unavailable.
- Container image pull timeout.
- DB chưa ready hoặc init script fail.
- Connection pool vượt giới hạn do nhiều Spring contexts.
- Reused container có data còn sót.
- Hai forks cùng dùng schema hoặc fixed container name.
- Shutdown/restart giữa test methods.
- CI runner không đủ disk/RAM.

**Đọc exception chain trước khi retry:** `Connection refused`, `TimeoutException`, `BindException`, `PSQLException`, `NoSuchBeanDefinitionException` là các hướng điều tra khác nhau. Đừng gắn tất cả nhãn flaky.

### 13.1. Phòng lỗi bằng readiness thay vì ngủ

Ví dụ fragment với Testcontainers PostgreSQL:

```java
@Container
static PostgreSQLContainer<?> postgres =
    new PostgreSQLContainer<>("postgres:16-alpine");

@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add(
        "spring.datasource.url", postgres::getJdbcUrl);
    registry.add(
        "spring.datasource.username", postgres::getUsername);
    registry.add(
        "spring.datasource.password", postgres::getPassword);
}
```

Đây là **mảnh cấu hình**, không thuộc runnable project ở mục 7 và cần Testcontainers/JDBC/PostgreSQL dependencies phù hợp, `@Testcontainers`, imports và lifecycle setup. Testcontainers cung cấp startup wait logic, dynamic host/port. Không hard-code `localhost:5432` cho random mapped port, và không dùng database production làm test target.

### 13.2. Cleanup trước retry phải idempotent

Nếu test gửi một external message, tạo đơn hàng, charge giả hoặc ghi object vào storage, lần đầu có thể **đã hoàn thành side effect** nhưng assertion fail vì timeout. Retry sẽ phát lần thứ hai:
- Duplicate message.
- Duplicate row/unique constraint error.
- Lệch số lần gọi mock/fake.
- Trùng audit event.
- Sai fixture vì cleanup chưa chạy.

Do đó một test integration retryable cần IDs riêng và thiết kế **idempotency/cleanup**. Với payment-like contract, không bao giờ để retry JUnit tự gửi lại transaction tài chính production thật. Dùng sandbox/test doubles, idempotency keys và policy network isolation.

## 14. Phân biệt lỗi ứng dụng thực với lỗi không ổn định của test

Một trong những nguy hiểm lớn nhất là gắn nhãn “flaky” cho sản phẩm có race. Ví dụ:
- Two concurrent `reserveStock()` calls đôi khi vượt inventory limit.
- HTTP client timeout trong điều kiện latency thực tế.
- Unique constraint race ở nhiều nodes.
- Outbox event đôi khi mất vì process crash.
- Cache invalidation/transaction callback đôi khi quá sớm.

Nếu rerun JUnit pass, nguyên nhân vẫn có thể là **production concurrency bug**. Cách tiếp cận:
1. Tìm minimal reproducer với controlled scheduling/fault injection.
2. Log correlation/trace IDs, input seed và DB isolation level.
3. Dùng stress tests hoặc concurrency testing framework riêng nếu cần.
4. Sửa invariants trong code (unique constraints, locks, transactions, idempotency), không chỉ thêm sleep.
5. Giữ regression test có thể deterministic bằng latch/barrier/fake clock.

**Bài học:** Retry giúp phân loại non-determinism, không cho phép mặc định quy trách nhiệm cho “CI chậm”.

## 15. Quarantine: được dùng nhưng phải có chủ sở hữu và đường quay về

Một flaky test không sửa ngay có thể làm mọi PR block, vì thế một số team chuyển nó sang **quarantine lane**. Nhưng quarantine sai cách nghĩa là **xóa coverage âm thầm**.

Một quy trình có trách nhiệm:
1. Tạo issue có owner, ngày phát hiện, failure signature, logs của first attempt, CI environment và link tới test.
2. Cung cấp lý do thực: test gây nhiễu nhưng không được bỏ vĩnh viễn; ghi rõ contract nào bị giảm coverage.
3. Quy định **expiration/review deadline** theo severity (ví dụ một sprint hoặc vài ngày cho critical path).
4. Đặt `@Tag("quarantine")` lên test class hoặc method theo JUnit tag policy.
5. Main `test` task dùng `excludeTags 'quarantine'`, **và** `quarantineTest` task chạy nhóm này thường xuyên (ví dụ nightly).
6. Thu thập tỷ lệ fail và issue owner; tạo dashboard để người quản lý nhìn thấy tests đang bị cách ly.
7. Khi sửa root cause, bỏ tag và đưa test về main gate; không duy trì hai bản test trùng nhau.

**Giới hạn của chính ví dụ:** `quarantineTest` task đã được đăng ký nhưng hiện không có test nào mang tag `quarantine`. Nếu chạy nó ngay, không có test được chọn; đây **không phải** “quarantine suite pass”. Muốn quan sát workflow, chỉ tag một test thật sự cần cách ly khi có issue và ownership.

### 15.1. Không dùng @Disabled như “quarantine vĩnh viễn”

`@Disabled` bỏ thực thi test; nhiều CI dashboards chỉ báo skipped và không cho thấy nó còn fail thế nào. Với `@Tag("quarantine")` và task riêng, test vẫn được chạy định kỳ để thu bằng chứng và phát hiện khi nó ổn định. Tuy nhiên nếu quarantine lane có `retry.maxRetries=0`, bạn quan sát được first failure rõ hơn; không để “quarantine + 10 retries” che nguyên nhân.

### 15.2. Quarantine khác bỏ gate cho bug nghiêm trọng

Không nên quarantine một test bắt lỗi security, double charging, data loss, authorization bypass hoặc schema migration phá dữ liệu chỉ vì nó khiến PR đỏ. Những ca nghiêm trọng cần **block release hoặc có mitigation chủ động**. Quyết định có được quarantine hay không phải dựa trên risk/coverage chứ không chỉ số phút CI bị chậm.

### 15.3. Policy maturity

| Mức | Cách xử lý | Hạn chế |
|---|---|---|
| M0: Rerun thủ công vô hạn | Người dùng bấm lại cho tới khi xanh | Che lỗi và tốn CI |
| M1: Bounded retry | Plugin maxRetries=1/2 | Có tín hiệu flakiness nhưng chưa quản lý |
| M2: Retry + strict gate + reporting | failOnPassedAfterRetry=true, lưu first failures | Có thể tăng build đỏ nếu legacy suite kém |
| M3: Owner/issue/quarantine TTL | Metrics và ưu tiên sửa | Tránh test bị bỏ vĩnh viễn |
| M4: Root-cause prevention | Clock injection, test isolation, deterministic async, environment contracts | Đầu tư kỹ thuật nhưng tăng độ tin cậy dài hạn |

Đích mong muốn không phải “retry nhiều hơn”, mà là **first-attempt pass rate cao và ít code/tài nguyên phụ thuộc trạng thái ngoài**.

## 16. Gắn nhãn và phân nhóm để không tốn retry không cần thiết

JUnit Jupiter `@Tag` có thể phân test thành `unit`, `integration`, `slow`, `external`, `quarantine`, `diagnostic`. Nhưng **tag selection và retry eligibility là hai lớp khác nhau**.

Trong build mẫu:
- `test` chạy tất cả Jupiter tests **trừ** `quarantine`, `diagnostic`.
- `diagnosticTest` chỉ chọn `diagnostic`.
- `quarantineTest` chỉ chọn `quarantine`.
- `check` từ Java plugin chạy `test`; không tự chạy hai custom tasks.

Trong một project lớn, có thể bổ sung:
- `unitTest`: không retry hoặc strict one retry để phát hiện lỗi hiếm.
- `integrationTest`: `maxRetries=1`, `maxFailures` thấp, môi trường riêng.
- `externalContractTest`: local stub cho PR; real contract ở sandbox job riêng.
- `flakyDiagnosticTest`: loop/repetition/stress riêng, không được tính như normal PR gate.
- `quarantineTest`: theo dõi issue, ban đầu failing được báo cáo rõ.

### 16.1. Bẫy khi CI chỉ chạy task test

Nếu một test bị chuyển vào `quarantineTest` nhưng CI không bao giờ gọi task đó, việc test vẫn nằm trong source code **không đồng nghĩa nó được thực thi**. Tương tự, một test dùng `@Tag("diagnostic")` bị loại khỏi `test`; cần biết task lựa chọn của nó.

Các báo cáo nên thống kê **tests discovered/selected/executed/skipped** theo từng task, không chỉ số source methods có `@Test` trong repo.

### 16.2. --tests không thay includeTags/excludeTags

```bash
./gradlew test --tests "*CheckoutServiceTest.fixedClockMakesProcessedDateStable"
```

Lệnh trên chạy một test trong `test` task. Nhưng nếu test mang tag `quarantine`, Gradle `--tests` không tự bỏ `excludeTags 'quarantine'` của task. Hãy gọi `quarantineTest --tests ...` để test đó được chọn đúng policy. Đây là phân biệt **test name filter** với **JUnit tag filter**.

## 17. CI: trình tự điều tra trước khi bật/tăng retries

### 17.1. Quy trình triage trong ngày

**Bước 1 — Giữ bằng chứng gốc.** Lưu full stack trace, test name, test reports, console output, Gradle worker ID/PID, commit SHA, Java/Gradle versions, DB/container versions, CI node details và nếu có thì random seed. Không rerun trước khi lưu failure đầu tiên.

**Bước 2 — Chọn một lớp failure.** `AssertionError` không đồng nghĩa test flaky. `Connection refused` ở 30 tests cùng lúc gợi ý hạ tầng. `ConcurrentModificationException` gợi ý shared state. `NoSuchBeanDefinitionException` có thể do context/config deterministic.

**Bước 3 — Reproduce hẹp.**
```bash
./gradlew test --tests "com.example.retrylab.CheckoutServiceTest"
```
Nên chạy đúng class/method và môi trường gần CI. Nếu không reproducible, thử thứ tự suites, parallel/forks, seed và resources.

**Bước 4 — Loại tác nhân ẩn.** Dùng fixed Clock, `@TempDir`, unique IDs, controlled executor/latch, dynamic ports, DB schema riêng, test fixture ownership.

**Bước 5 — Kiểm tra regression.** Sau sửa, chạy targeted test nhiều lần có deadline, rồi toàn suite song song và CI tương ứng. Không chỉ chạy một lần trên laptop.

**Bước 6 — Đóng issue bằng bằng chứng.** Có link PR, root cause, first-attempt pass rate theo một khoảng đo đủ, đã bỏ quarantine tag và đảm bảo test được include trong `check`.

### 17.2. Tái hiện một thất bại chỉ xuất hiện khi chạy đủ suite

```bash
./gradlew clean test --max-workers=1
./gradlew clean test --max-workers=4
```

Hai lệnh này khác tổng Gradle worker budget, nhưng nếu `maxParallelForks=1` trong build mẫu thì `test` vẫn chỉ có một fork. Để kiểm chứng cross-process contention, phải **thay task maxParallelForks** ở một test branch/Gradle property phù hợp, không suy ra do thay `--max-workers` một mình.

Nếu dự án có JUnit parallel enabled trong `junit-platform.properties`, việc giảm Gradle forks không tự tắt Jupiter concurrent threads. Tách từng tầng giúp tìm root cause.

### 17.3. Một lỗi Spring context không nên retry

Nếu `@SpringBootTest` fail vì thiếu property bắt buộc hoặc bean không được tạo do `@ConditionalOnClass`, đó có thể là config lỗi nhất quán. Retry không sửa classpath. Kiểm tra `ConditionEvaluationReport`, active profiles, `@DynamicPropertySource`, configuration imports và stack trace trước khi xem đây là flaky test.

## 18. Retry metrics và SLO cho chất lượng test

Để biết hệ thống CI đang tốt lên hay chỉ “xanh nhờ retry”, theo dõi:

| Metric | Định nghĩa | Tại sao cần |
|---|---|---|
| First-attempt failure rate | Failures/lượt chạy đầu của tests | Đo tín hiệu gốc |
| Pass-after-retry rate | Test failures sau đó pass / tests từng fail | Đo flakiness biểu hiện |
| Permanently failed test count | Tests vẫn fail sau attempts tối đa | Phân biệt unresolved failures |
| Retry amplification | Tổng test executions / unique selected tests | Đo chi phí do retry |
| Quarantine inventory | Số tests quarantined, owner, deadline | Đo coverage bị giảm |
| Mean time to fix flaky issue | Thời gian từ phát hiện tới sửa gốc | Đo tốc độ xử lý |
| CI build wall-clock p50/p95 | Thời lượng job theo phân vị | Phát hiện retry làm CI chậm |
| Skipped/untagged count | Tests không được thực thi vì filter/disable | Tránh coverage biến mất |
| Environment incident count | Docker/DB/runner outages gây nhiều test failures | Tách hạ tầng và test quality |

Không lấy `build pass rate` làm metric duy nhất. Nếu bật `failOnPassedAfterRetry=false`, tỷ lệ pipeline xanh có thể tăng tức thì trong khi first-attempt failures không cải thiện.

### 18.1. Ví dụ dashboard/issue cần ghi gì?

Một record triage hợp lý:
- Test: `com.example...AsyncReceiptServiceTest.asyncResultIsWaitedForRatherThanSleptFor`.
- First failure: `TimeoutException` sau deadline, timestamp và stack trace.
- Retry result: pass hoặc fail; số attempts; không chỉ final status.
- Environment: CI runner CPU quota, Java 17 version, Gradle, test fork/parallel settings.
- Suspected cause: executor starvation, thread leak, dependency readiness hoặc timeout không phù hợp.
- Owner, issue link, severity, date detected, deadline.
- Evidence of fix: PR commit + repeated targeted/full-suite CI runs.
- Quarantine status: active/expired/removed with rationale.

Không lưu production credentials, PII hoặc customer payload trong artifacts/logs để điều tra test.

## 19. Một chính sách “quarantine có thời hạn” có thể áp dụng

Gợi ý policy cho một team:
1. Chỉ mở quarantine khi first-attempt fail có đủ evidence và lỗi không thuộc critical security/data integrity contract.
2. Issue phải có owner và ngày review; không chấp nhận “flaky, ignore”.
3. `quarantineTest` phải chạy nightly hoặc tối thiểu lịch định kỳ; không biến thành dead code.
4. Retry của quarantine lane có thể đặt `0` để nhìn thấy first failure; thử repeated/stress trong separate diagnostic job.
5. Build release phải có quy định cho known flaky critical paths; không mặc nhiên cho release xanh.
6. Quarantine quá hạn cần escalation, không tự động gia hạn vô hạn.
7. Fix root cause và xóa quarantine tag; xác minh test quay lại normal gate.
8. Theo dõi tỷ lệ flaky mới và thời gian sửa, không đo team chỉ bằng số lần build xanh.

**Đây là policy mẫu, không phải quy định của một tổ chức cụ thể.** Team có thể điều chỉnh thời hạn hoặc severity thresholds, nhưng nên giữ nguyên nguyên tắc **không che giấu failures và không mất test coverage**.

## 20. Troubleshooting các cấu hình retry

| Triệu chứng | Nguyên nhân có thể | Hành động |
|---|---|---|
| Đã apply plugin nhưng test không retry | `maxRetries=0` mặc định hoặc CI env không có | Kiểm tra `retry` trên đúng `Test` task |
| Local không retry, CI có | Build có `onCi` branch | Đây là policy chủ đích trong sample |
| `maxRetries=1` tưởng hai lần retry | Hiểu sai từ “retry” | Initial + **một** attempt bổ sung |
| Test fail→pass nhưng Gradle task đỏ | `failOnPassedAfterRetry=true` | Đúng policy strict; sửa flaky test |
| Test fail→pass nhưng Gradle task xanh | `failOnPassedAfterRetry=false` hoặc gate reporter khác | Kiểm tra policy/report, đừng bỏ failure |
| Không retry khi cả suite fail hàng loạt | `maxFailures` threshold | Kiểm tra DB/Docker/runner outage |
| `@ParameterizedTest` chạy lại cả bộ arguments | Retry granularity ở method level | Thiết kế idempotent và chia cases nếu cần |
| `@RepeatedTest(5)` chạy năm lần dù pass | Repetition là kế hoạch chứ không retry | Để diagnostic task riêng |
| `--rerun-tasks` chạy nhiều tests | Rerun Gradle task, không failing-only | Dùng --tests hoặc plugin cho mục tiêu cụ thể |
| `--tests` không thấy test | Name filter + tags/exclusions | Chọn đúng task và kiểm tra filters |
| IDE run không retry nhưng Gradle run có | IDE không delegate chạy test tới Gradle | Dùng Gradle task khi kiểm chứng retry policy |
| XML báo fail dù Gradle task xanh | CI XML parser đọc failed first attempt | Xem `mergeReruns` và CI interpretation |
| XML nhìn xanh nhưng test có flaky | XML parser bỏ qua `<flakyFailure>` | Dùng dashboard hiểu flaky hoặc giữ mergeReruns=false |
| Retry nhưng không sửa dữ liệu bẩn | Side effect đầu chưa cleanup | Dùng unique IDs, rollback/cleanup, idempotency |
| Spring context fail sau lần đầu | Shared state, `@DirtiesContext`, Mockito overrides | Isolation/serial lane |
| Retry pass sau khi tăng Thread.sleep | Race bị che tạm thời | Dùng latch/Future/Awaitility với deadline |
| Time-dependent test fail gần nửa đêm | Dùng wall clock | Inject `Clock.fixed` |
| Test chỉ fail khi nhiều forks | Shared DB/file/port/containers | Per-fork resources, @TempDir |
| Test timeout trên CI | CPU throttling, deadlock, network | Capture thread dumps/futures, fix root cause |
| External provider trả 429 | Rate limiting/quotas | Stub unit; sandbox contract policy riêng |
| Build xanh nhưng tests không chạy | `UP-TO-DATE`, `FROM-CACHE`, filters/no-source | Đọc task state và test reports |
| Retry tăng thời gian CI nhiều lần | Too many retries/expensive fixture startup | Giảm attempts, fix root causes |
| Plugin filter không khớp method annotation | Filter dựa reported class names/annotations | Dùng đúng filter API, không nhầm JUnit tags |
| Quarantine tests không được chạy | Không có scheduler/job gọi quarantineTest | Bổ sung nightly task và report |
| Test fail nhưng bị skip khi retry | Conditional disable or engine change | Giữ `failOnSkippedAfterRetry=true` và điều tra |

## 21. Lệnh chạy và kiểm chứng đúng

Với project đã tạo và có Gradle wrapper tương thích:

```bash
# Local (không có CI env): chạy các tests bình thường, retry tắt
./gradlew test

# Chạy một test method để debug
./gradlew test --tests "com.example.retrylab.CheckoutServiceTest.fixedClockMakesProcessedDateStable"

# Lệnh CI trên shell POSIX: bật retry qua biến môi trường
CI=true ./gradlew test

# Diagnostic lane: một @RepeatedTest với 5 invocations
./gradlew diagnosticTest

# Chạy verification lifecycle (test, không tự chạy diagnostic)
./gradlew check

# Cố tình yêu cầu Gradle chạy tasks lại thay vì dùng up-to-date
./gradlew test --rerun-tasks
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests "com.example.retrylab.CheckoutServiceTest.fixedClockMakesProcessedDateStable"

$env:CI = "true"
.\gradlew.bat test
Remove-Item Env:CI

.\gradlew.bat diagnosticTest
```

**Chú ý:** Build mẫu **không tự cung cấp Gradle wrapper files**, nên các lệnh `./gradlew` chỉ chạy nếu project có wrapper tương thích; nếu chưa có và máy đã cài Gradle, có thể chạy `gradle wrapper`. Đừng suy ra stdout chính xác; môi trường cần Java 17 toolchain và dependencies tải từ repository (lần đầu cần network để resolve dependency, nhưng tests không cần external app services). Từ “không cần dịch vụ ngoài” chỉ mô tả **runtime của tests**, không hứa build chạy offline khi dependency chưa được cache.

### 21.1. Đếm source tests và invocations

| Task | Source được chọn | Số ca thiết kế |
|---|---|---:|
| `test` | CheckoutServiceTest + AsyncReceiptServiceTest + ReceiptFileWriterTest + CheckoutSpringTest | **11 `@Test` methods** |
| `diagnosticTest` | StabilityRepetitionTest | **1 `@RepeatedTest` method, 5 invocations** |
| `quarantineTest` | Không có test mang tag quarantine ban đầu | **0 selected tests** |
| `check` | Java plugin `test` dependency | **11 `@Test` methods** trong sample |
| `test` khi có first-attempt failure và CI retry | Cùng test selection ban đầu + retries của tests fail | Executions có thể nhiều hơn 11 |

Các số trong bảng dựa vào **source sample và task filters**, không phải số đã được thực thi xác nhận. Khi dùng `@ParameterizedTest`, `@RepeatedTest`, dynamic tests hoặc retries, phải phân biệt **test methods**, **JUnit invocations** và **tổng execution attempts**.

### 21.2. Kiểm tra artifacts theo task

```text
build/reports/tests/test/index.html
build/test-results/test/

build/reports/tests/diagnosticTest/index.html
build/test-results/diagnosticTest/

build/reports/tests/quarantineTest/index.html
build/test-results/quarantineTest/
```

Khi test bị retry, đọc **tất cả attempts**, không chỉ final green. Nếu `test` task `UP-TO-DATE` trong một build không có input changes, đó không phải một lần retry hay chứng minh first-attempt pass trong run hiện tại. Khi cần reproducibility, chạy targeted test với `--rerun-tasks`, thu logs và giữ CI environment fingerprint.

### 21.3. Test retry plugin có thể hiện thực mà không khiến normal suite flaky

Để kiểm tra plugin thật sự hoạt động, hãy tạo **một integration fixture độc lập** trên branch/test project dành riêng cho plugin validation:
1. Có một test được điều khiển bởi input/marker rõ ràng để fail ở first attempt rồi pass ở retry, **không dùng random probability**.
2. Chạy fixture qua Gradle với `maxRetries=1`.
3. Assert Gradle build status đúng `failOnPassedAfterRetry` và XML report hiển thị hai executions.
4. Xóa fixture hoặc giữ trong một dự án plugin-test riêng, không chạy trong main application `test`.
5. Không dùng JVM static counter làm tín hiệu duy nhất nếu retry tạo process/classloader khác; state cần được kiểm soát theo contract của fixture.

Đây là hướng dẫn thử nghiệm riêng, **không phải bài test được chạy trong project mẫu**. Mục đích là tránh dạy một lớp flaky giả tạo rồi đưa nhầm nó vào PR gate.

## 22. Những hành vi cần giữ sau khi sửa flaky test

Một bản sửa chất lượng không chỉ “tăng timeout”. Hãy đánh giá:
- Test còn kiểm tra đúng yêu cầu nghiệp vụ hay đã nới assertion đến mức bug cũng pass?
- Chỉ ra được **root cause**: clock, shared state, async completion, DB transaction, context cache, port conflict, external dependency?
- Có kiểm chứng độc lập/parallel đúng với CI?
- Cleanup có chạy ở `finally`/`@AfterEach` và không xóa state của test khác?
- Có sử dụng unique IDs/schema/path để ngăn cross-test interference?
- `@DirtiesContext` có thực sự cần thiết và không phá cached context của tests concurrent?
- Có giữ lại first-failure artifacts để đối chiếu trước/sau sửa?
- Quarantine tag đã được gỡ, task `test` hoặc đúng verification lane đã chọn test?
- Tests có được thực thi thật, không bị cache/skip/NO-SOURCE?
- CI metrics cho thấy first-attempt pass rate tốt lên thay vì chỉ tăng tỷ lệ xanh sau retry?

**Không sửa một test flaky bằng cách xóa assertion quan trọng, dùng `@Disabled` vô thời hạn hoặc tăng retry đến khi nó thường xanh.** Điều đó đổi một tín hiệu chất lượng thành khoảng trống coverage.

## 23. Checklist vận hành CI

- [ ] Mỗi lần fail lưu stack trace và report **lần đầu** trước khi retry/rerun job.
- [ ] Phân biệt deterministic bug, flaky test, intermittent product failure, environment outage.
- [ ] Hiểu `maxRetries=1` là **initial attempt + 1 retry**.
- [ ] Chỉ bật retry ở những Gradle `Test` tasks có policy rõ ràng.
- [ ] Đặt `maxFailures` để tránh retry storm khi nhiều tests fail do môi trường.
- [ ] Xác định rõ `failOnPassedAfterRetry` và `failOnSkippedAfterRetry`.
- [ ] Không đặt `ignoreFailures=true` để che lỗi.
- [ ] Không coi `@RepeatedTest` là Gradle retry-on-failure.
- [ ] Không coi `--rerun-tasks` là retry failing-only tests.
- [ ] Không dùng nhiều tầng retry (JUnit/Gradle/CI) thiếu ngân sách attempts.
- [ ] Biết `@ParameterizedTest` có thể retry toàn method.
- [ ] Không có tests gửi production email/payment/message khi bị retry.
- [ ] Không dùng `Thread.sleep` để giả định async completion.
- [ ] Chờ Future/latch/Awaitility với deadline và assert outcome thật.
- [ ] Inject `Clock`, kiểm soát random seeds/timezone.
- [ ] Dùng `@TempDir`/unique test IDs và cleanup ownership.
- [ ] Không dùng `@ResourceLock` như distributed lock giữa Gradle forks.
- [ ] Spring context, `@DirtiesContext`, Mockito overrides và DB fixtures được cô lập.
- [ ] Nhận biết `@Transactional` test thread không bao phủ HTTP/async thread.
- [ ] Testcontainers readiness/dynamic ports được xử lý đúng.
- [ ] Quarantine có issue, owner, deadline và scheduled execution.
- [ ] Quarantine không che security/data integrity regression.
- [ ] HTML/XML reports cho mọi test task được publish đầy đủ.
- [ ] Hiểu `mergeReruns` tác động tới CI XML parser.
- [ ] Giữ metrics first-attempt failures và pass-on-retry count.
- [ ] `UP-TO-DATE`/`FROM-CACHE` không bị báo thành một execution mới.
- [ ] Kiểm tra root cause và rerun đủ representative CI sau khi sửa.
- [ ] Không tuyên bố runtime tests đã pass khi chưa thực sự chạy Gradle/JUnit.

## 24. Nguồn chính thức và đọc thêm

- [Gradle Test Retry Plugin — Gradle Plugin Portal 1.6.6](https://plugins.gradle.org/plugin/org.gradle.test-retry/1.6.6): plugin ID, phiên bản, cách apply trong Groovy/Kotlin DSL.
- [Gradle Test Retry Plugin — README chính thức](https://github.com/gradle/test-retry-gradle-plugin): `maxRetries`, `maxFailures`, `failOnPassedAfterRetry`, filter, parameterized retry, reporting.
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): `Test` tasks, `--tests`, reports, `mergeReruns`, `failFast`, `ignoreFailures`.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): `--rerun-tasks`, `--max-workers`, `--continue`, task selection.
- [JUnit Jupiter — Repeated Tests](https://docs.junit.org/5.14.2/writing-tests/repeated-tests.html): `@RepeatedTest`, `RepetitionInfo`, invocation counts.
- [JUnit Jupiter — Tagging and Filtering](https://docs.junit.org/5.14.2/writing-tests/tagging-and-filtering.html): `@Tag`, include/exclude nhóm diagnostic/quarantine.
- [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/): `@SpringBootTest`, test slices, Spring Boot starter-test.
- [Spring Framework — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/parallel-test-execution.html): Spring context cache, `@DirtiesContext`, mock overrides, shared state.
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): rollback, thread boundaries và `TestTransaction`.
- [Testcontainers — Java Quickstart](https://java.testcontainers.org/quickstart/junit_5_quickstart/): container lifecycle, JUnit 5 support và readiness.
- [Gradle Blog — Handling Flaky Tests](https://blog.gradle.org/how-we-handle-flaky-tests-in-gradle): retry và quy trình phân loại failures.

**Kết luận:** Khi JUnit test fail lần đầu rồi pass khi chạy lại, đó là **tín hiệu cần điều tra**, không phải bằng chứng hệ thống đã ổn. `Gradle Test Retry Plugin` cho phép retry có giới hạn và ghi lại attempts; `failOnPassedAfterRetry=true` giúp CI không âm thầm che flakiness. `@RepeatedTest`, `--rerun-tasks` và CI rerun job giải quyết các mục tiêu khác nhau. Sửa nguyên nhân gốc bằng test isolation, fixed clock, controlled async completion, DB/transaction boundary, resource readiness và dữ liệu độc lập; chỉ dùng quarantine có ownership/thời hạn, đồng thời theo dõi first-attempt pass rate và reports. Một pipeline đáng tin cậy là pipeline **phát hiện lỗi thật một cách nhất quán**, chứ không phải pipeline xanh nhờ thử lại cho tới khi may mắn.
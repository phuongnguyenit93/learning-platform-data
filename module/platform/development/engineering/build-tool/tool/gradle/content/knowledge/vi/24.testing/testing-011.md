# Phân biệt task cache hit với kiểm thử thực sự được thực thi lại

**Chủ đề:** Build Tool Gradle  
**Nhóm kiến thức:** Kiểm thử

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Nhìn kết quả của một Gradle **Test task** và phân biệt **UP-TO-DATE**, **FROM-CACHE**, **task thực thi thật**, **NO-SOURCE**, **SKIPPED** và **FAILED**.
2. Hiểu **Gradle build cache** lưu/khôi phục **task outputs**, trong đó có test results/reports, chứ không ghi lại một lần gọi mới các phương thức JUnit chỉ vì bạn gõ lệnh test.
3. Giải thích vì sao **BUILD SUCCESSFUL** không đồng nghĩa “mọi bài test được chạy lại”, và vì sao **test reports/đếm test cases** có thể là kết quả của một lượt chạy cũ.
4. Phân biệt **up-to-date check**, **build cache**, **configuration cache** và **test retry**; không nhầm những cơ chế khác nhau chỉ vì chúng đều làm build nhanh hơn.
5. Dùng đúng các cờ **--build-cache**, **--no-build-cache**, **--rerun-tasks**, **--rerun** (nếu Gradle version hỗ trợ), **clean**, **--tests** và **--test-dry-run**.
6. Tự chạy một dự án **Gradle Groovy DSL + Java 17 + JUnit Jupiter**: build baseline, tạo cache, làm mất outputs, quan sát **FROM-CACHE** rồi ép test thực sự chạy và nhìn test events.
7. Biết cách xác minh một bài test đã chạy trong **lượt build hiện tại**: task outcome, sự kiện test mới, logs đúng invocation và điều kiện không bị skip/dry-run.
8. Phân tích rủi ro khi cache test phụ thuộc vào **đồng hồ, ngẫu nhiên, môi trường, database ngoài, mạng, filesystem bên ngoài hoặc secrets**, và lựa chọn chiến lược phù hợp cho unit tests, integration tests và CI.
9. Thiết kế một checklist thực tế để trả lời câu hỏi “Tôi vừa chạy ./gradlew test — các bài test có thực sự chạy lại không?”

**Điểm mấu chốt:** Gradle có thể báo **BUILD SUCCESSFUL** vì đầu ra của Test task đã hợp lệ từ lần trước (**UP-TO-DATE**) hoặc đã được phục hồi từ cache (**FROM-CACHE**). Trong cả hai tình huống, **không có lượt thực thi JUnit tests mới từ Test task đó**. Muốn khẳng định “tests được chạy lại”, cần chứng minh task **không dùng hai đường tối ưu ấy** và các test cases thực sự được thực thi, chứ không chỉ nhìn chữ SUCCESS.

## 1. Câu hỏi chính: kết quả có mới hay chỉ được tái sử dụng?

Hãy xét ba lượt chạy cùng lệnh:

~~~bash
./gradlew test
./gradlew test
./gradlew test
~~~

Không có thay đổi source hay environment. Một lượt đầu có thể chạy Test task thật; lượt kế tiếp Gradle có thể quyết định output và inputs không đổi, nên đánh dấu **UP-TO-DATE**. Nếu build cache bật và outputs không còn trong workspace nhưng kết quả cũ tương ứng có trong cache, Gradle có thể phục hồi outputs và đánh dấu **FROM-CACHE**.

Cả ba lượt có thể trả:

~~~text
BUILD SUCCESSFUL
~~~

nhưng **ý nghĩa hoàn toàn khác nhau**:

| Tình huống | Test task có gọi JUnit engine thực sự trong lượt này? | Đầu ra có thể vẫn hiện diện? |
|---|---|---|
| Test task thực thi bình thường | **Có**, nếu tests được khám phá và chạy | Có, do lượt chạy hiện tại tạo |
| Test task **UP-TO-DATE** | **Không** | Có, outputs cũ trong workspace |
| Test task **FROM-CACHE** | **Không** | Có, outputs được phục hồi từ cache |
| Test task **NO-SOURCE** | **Không** | Có thể không có test result mới |
| Test task **SKIPPED** | **Không** (do điều kiện task/disable) | Không suy được chỉ từ nhãn |
| Test task **FAILED** | Có thể đã chạy một phần tests hoặc thất bại trước khi chạy | Có thể có report của các tests hoàn thành |

**Cẩn thận:** Một Test task được thực thi thật **vẫn có thể không chạy test case nào** nếu filter loại hết, không có test classes, dry-run mode hoặc điều kiện đặc biệt. Vì vậy có hai câu hỏi riêng:

1. **Task action có thực thi trong lượt này không?**
2. **JUnit/TestNG test cases nào thực sự được thực thi trong lượt này?**

Cần câu trả lời **cả hai** khi làm QA hoặc điều tra CI.

### 1.1. Build thành công không phải bằng chứng test vừa chạy

Ví dụ Gradle hiển thị:

~~~text
> Task :compileJava UP-TO-DATE
> Task :compileTestJava UP-TO-DATE
> Task :test FROM-CACHE

BUILD SUCCESSFUL
~~~

Điều chắc chắn: Gradle đã lấy **kết quả của task :test** từ build cache, không chạy lại các test methods bằng JUnit trong lượt invocation ấy. Test reports có thể xuất hiện đúng đường dẫn và có số tests passed, nhưng đó là **kết quả được tạo trong một build trước** với những inputs được Gradle coi là tương đương.

Nếu pipeline chỉ yêu cầu “có kết quả test phù hợp với code/inputs hiện tại”, cache hit có thể hoàn toàn hợp lý. Nếu quy trình yêu cầu **gọi lại hệ thống ngoài ngay bây giờ** hoặc **đo lại sự ổn định hiện tại**, cache hit **không đáp ứng** yêu cầu đó.

### 1.2. Nhớ ba câu ngắn

- **UP-TO-DATE** = outputs vẫn ở nơi cũ, task không cần thực thi.
- **FROM-CACHE** = outputs được lấy lại từ cache, task không cần thực thi.
- **Task executed** = Gradle đã thực hiện task actions; còn có test cases chạy thật hay không phải kiểm tra tiếp.

Đừng dùng các câu “task đã chạy” và “task nằm trong task graph” như hai cách nói tương đương. Một task có thể nằm trong graph nhưng bị bỏ qua nhờ tối ưu hoặc điều kiện.

## 2. Cơ chế Gradle kiểm tra Test task

Gradle Java Plugin tạo source set **test**, các dependency configurations như testImplementation/testRuntimeOnly và task **test** thuộc kiểu **org.gradle.api.tasks.testing.Test**. Test task có thông tin quan trọng:

- **testClassesDirs**: những thư mục chứa compiled test classes.
- **classpath**: classpath chạy tests gồm classes dưới kiểm thử, test framework và dependencies.
- **Test framework options**: ví dụ useJUnitPlatform(), engine/tag filters.
- **Các input khác**: JVM/test task settings, thuộc tính mà Gradle/task/plugin thực sự khai báo.
- **Outputs**: kết quả dạng binary, XML, HTML reports theo cấu hình.

Gradle dùng fingerprints của task implementation và **các inputs đã biết** để quyết định task có cần chạy hay có cache result tương ứng không.

### 2.1. Up-to-date checks

Nếu task từng thực thi thành công trong workspace, outputs còn hợp lệ và những inputs có ảnh hưởng không đổi, Gradle có thể **UP-TO-DATE**. Khi đó:

- Không khởi chạy test worker JVM mới cho task vì không cần thực thi tests.
- Không gọi lại @Test methods.
- Thông thường test XML/HTML/binary results từ lượt trước vẫn còn.
- Thời gian build ngắn hơn đáng kể.

**Không cần bật build cache để có UP-TO-DATE.** Up-to-date checks là tối ưu cơ bản của Gradle. Ngay cả khi chạy **--no-build-cache**, Test task vẫn có thể **UP-TO-DATE**.

### 2.2. Build cache

Gradle build cache cho phép dùng **task outputs từ một lần thực thi trước**, có thể ở workspace khác hoặc CI runner khác nếu cache được chia sẻ.

Quy trình khái niệm:

~~~text
                  Test task được yêu cầu
                           |
                           v
               Gradle xét inputs/outputs
                           |
          +----------------+----------------+
          |                                 |
  Outputs local vẫn hợp lệ            Task cần kết quả
          |                                 |
          v                                 v
      UP-TO-DATE                      Build cache bật?
          |                          /             \
          |                        Có             Không
          |                        |                |
          |                   Cache key khớp?       |
          |                    /      \             |
          |                   Có      Không          |
          |                   |         |            |
          v                   v         v            v
  Không chạy tests        FROM-CACHE   Thực thi Test task/JUnit
                                    (nếu test cases có)
~~~

Sơ đồ đơn giản hóa; Gradle cũng có điều kiện skip, cacheability, task validation, forced execution và các lý do khác. Nhưng nó nhấn mạnh: **FROM-CACHE là lấy outputs, không gọi test runner**.

### 2.3. Cache có bật mặc định không?

Trong Gradle 9.9, **build cache không bật mặc định**, trừ khi build/user đã đặt cấu hình khác. Bạn có thể bật theo invocation:

~~~bash
./gradlew test --build-cache
~~~

hoặc đặt trong gradle.properties:

~~~properties
org.gradle.caching=true
~~~

Vô hiệu hóa cho invocation:

~~~bash
./gradlew test --no-build-cache
~~~

**Test là một built-in cacheable task type** trong Gradle. Nhưng cache **chỉ thực sự được sử dụng** nếu build cache được bật, task đủ điều kiện cache, cache key/outputs phù hợp và không có rule vô hiệu hóa cache.

Không nên nói “mọi Test task sẽ FROM-CACHE khi bật cache” vì lần đầu chưa có entry, inputs đổi, cache miss hoặc task bị loại khỏi cache hoàn toàn đều có thể khiến task chạy.

### 2.4. Local cache và remote cache

**Local build cache**: Gradle giữ outputs/cache entries trên máy hiện tại.

**Remote build cache**: chia sẻ outputs giữa CI agents/developers, nếu tổ chức đã cấu hình và cho phép đọc/ghi remote cache.

Cả hai đều có thể dẫn đến **FROM-CACHE**; nhãn này **không tự nói cache entry đến từ local hay remote**. Nếu cần biết nguồn, hãy xem build cache/debug/Build Scan logs theo hạ tầng thực tế.

**Cache hit = task outputs được tái sử dụng**. Nó không có nghĩa test vừa chạy trên máy developer hoặc máy CI hiện tại.

### 2.5. Cache key không phải “hash của commit Git”

Gradle tính cache key dựa trên thông tin task implementation và những inputs nó đã biết, chẳng hạn:
- Compiled test classes.
- Classpath liên quan (app/library/test framework).
- Cấu hình test task được khai báo là input.
- Toolchain/Gradle/plugin/task implementation và các input properties ảnh hưởng kết quả.
- Task-specific file inputs/outputs được mô hình hóa phù hợp.

**Không thể nói hai Git commits khác nhau chắc chắn là hai cache keys khác nhau**, vì thay đổi README hay một file không liên quan đến Test inputs có thể không đổi cache key. Ngược lại, cùng Git commit nhưng JVM/test settings khác cũng có thể khiến cache miss nếu thay đổi nằm trong những inputs Gradle theo dõi.

**Ranh giới quan trọng:** Một test đọc môi trường ngoài mà build không khai báo thành input (thời gian thực, API server, database đang đổi, file ngoài project) có thể nhận **cache hit cho kết quả đã cũ**. Đây là vấn đề *test determinism/input modeling*, không phải Gradle “sai” khi tái sử dụng kết quả dựa trên inputs nó được cung cấp.

## 3. Đọc task outcome đúng cách

### 3.1. Những outcome cần phân biệt

| Dòng Gradle | Task actions có được thực thi lại? | Ý nghĩa |
|---|---|---|
| > Task :test | Thường có nếu không bị skip/không ở dry-run | Thực thi task trong lần build này, nhưng cần xem số test cases thật |
| > Task :test UP-TO-DATE | **Không** | Inputs và outputs local được coi là hợp lệ |
| > Task :test FROM-CACHE | **Không** | Outputs phục hồi từ build cache |
| > Task :test NO-SOURCE | **Không có tests được chạy** | Không có source/test input phù hợp để chạy |
| > Task :test SKIPPED | **Không** | Task bị skip do điều kiện/disable, không phải cache hit |
| > Task :test FAILED | Có thể có, nhưng có thể thất bại trước khi chạy bất kỳ test nào | Đọc test report/stacktrace để xác định |
| > Task :test (với --test-dry-run) | **Không có test methods được gọi thật** | Task có thể sinh mô phỏng reports, không phải test execution thực |

**Chú ý:** Gradle console có thể dùng rich console, kết hợp progress logs, in các dòng khác nhau tùy Gradle version/cờ --console. Dùng **--console=plain** để output dễ đọc khi kiểm tra CI. Nội dung cuối “BUILD SUCCESSFUL in ...” chỉ là kết quả tổng quát của build, không cung cấp bằng chứng tests vừa chạy.

### 3.2. Tại sao không chỉ đọc báo cáo HTML?

Gradle Test task thường xuất report:

~~~text
build/reports/tests/test/index.html
build/test-results/test/TEST-...xml
build/test-results/test/binary/...
~~~

Nếu task **FROM-CACHE**, các outputs có thể được phục hồi và report vẫn có:
- Tests: 2
- Failures: 0
- Skipped: 0
- Success rate: 100%

Đó là thông tin về **kết quả test được tái sử dụng**, **không phải timestamp chứng minh hai test methods vừa chạy**. Nhiều công cụ CI đọc XML và hiển thị kết quả bình thường dù task không thực thi trong lượt này.

Khi yêu cầu “tests chạy thật trong phiên CI hiện tại”, cần kết hợp **task execution outcome + test events mới + bản ghi invocation**, không chỉ số liệu trong report.

### 3.3. Test event khác task outcome

- **Task :test UP-TO-DATE** nghĩa là *cả task* được bỏ qua.
- **JUnit test skipped/disabled** nghĩa là *một test case* bị bỏ qua bởi framework/annotation/filter, ngay cả khi task :test có thể vẫn thực thi những test khác.
- **Task :test FAILED** có thể do một test assertion fail, hoặc do môi trường khiến worker JVM không khởi chạy.
- **Task :test FROM-CACHE** có thể khôi phục report chứa những test cases từng được đánh dấu skipped; nó không có nghĩa framework mới quyết định skip các case ấy.

Tầng task và tầng individual test case là **hai cấp khác nhau**.

## 4. Ba nhóm cờ CLI dễ nhầm

### 4.1. --build-cache và --no-build-cache

~~~bash
./gradlew test --build-cache
./gradlew test --no-build-cache
~~~

- **--build-cache** cho phép cache lookup/store nếu task cacheable và eligible.
- **--no-build-cache** tắt task output cache lookup/store cho invocation.

Nhưng:

~~~bash
./gradlew test --no-build-cache
~~~

**KHÔNG đảm bảo test chạy lại.** Nếu inputs/outputs local không đổi, task vẫn có thể **UP-TO-DATE**. Đây là một trong những nhầm lẫn phổ biến nhất.

### 4.2. --rerun-tasks

~~~bash
./gradlew test --rerun-tasks
~~~

Theo Gradle CLI, **--rerun-tasks** buộc các tasks trong task graph của invocation chạy lại, bỏ qua up-to-date checks và build cache lookup tương ứng. Điều này cũng ảnh hưởng **task dependencies của :test**, ví dụ compileJava/compileTestJava, nên có thể tốn thời gian hơn mong đợi.

**Giới hạn:** Nó không biến task bị disabled/onlyIf false thành enabled, không tạo test classes khi source set rỗng, không vượt qua test filters hay --test-dry-run, và không sửa lỗi test framework missing. Vì vậy đây là cờ mạnh để **bắt Gradle xử lý lại task**, nhưng phải kiểm chứng có test cases được chạy thật.

Để biểu đạt rõ ràng và tránh cache gây nhiễu trong bài thực hành:

~~~bash
./gradlew test --rerun-tasks --no-build-cache --console=plain
~~~

**--no-build-cache** trong câu lệnh này là phần diễn đạt ý định và hỗ trợ quan sát, còn --rerun-tasks tự nó đã bỏ qua những cơ chế tối ưu task outputs cần thiết theo CLI Gradle hiện hành.

### 4.3. --rerun của một task (nếu phiên bản Gradle hỗ trợ)

Gradle hiện hành có **built-in task option --rerun** dùng với task cụ thể:

~~~bash
./gradlew test --rerun
~~~

Nó giúp ép **task test** chạy lại mà không buộc mọi task dependency cùng rerun như --rerun-tasks. Hãy kiểm tra bản Gradle của bạn bằng:

~~~bash
./gradlew help --task test
~~~

Nếu Gradle Wrapper/CLI không hỗ trợ --rerun cho task, dùng **--rerun-tasks** hoặc chiến lược cấu hình phù hợp; đừng suy rằng mọi phiên bản Gradle cũ có cùng task option này.

### 4.4. clean không chắc là một lượt test execution mới

Lệnh:

~~~bash
./gradlew clean test --build-cache
~~~

xóa build outputs local rồi chạy test. Nhưng nếu cache chứa kết quả cùng input fingerprint, :test **có thể FROM-CACHE**. Do đó câu “đã clean rồi chắc chắn test chạy thật” là **sai khi bật build cache**.

So sánh:

| Câu lệnh | Có thể UP-TO-DATE? | Có thể FROM-CACHE? | Có thể thực thi JUnit thực? |
|---|---|---|---|
| ./gradlew test | Có | Có nếu cache được bật qua settings | Có nếu task cần chạy |
| ./gradlew test --no-build-cache | Có | Không | Có nếu không up-to-date/skip |
| ./gradlew clean test --build-cache | Thường không giữ local test outputs sau clean | **Có** | Có nếu cache miss |
| ./gradlew clean test --no-build-cache | Không dựa trên outputs local cũ đã xóa | Không | **Có** nếu task có tests và không bị skip/dry-run |
| ./gradlew test --rerun-tasks | Không dùng normal up-to-date shortcut | Không dùng normal cache shortcut | **Có** nếu task hợp lệ và test cases được chọn |
| ./gradlew test --rerun | Không dùng normal shortcut cho task test (nếu hỗ trợ) | Không dùng cache shortcut cho task test | **Có** nếu task hợp lệ và test cases được chọn |

Các từ “thường”, “có thể” quan trọng: outcomes còn phụ thuộc plugin, test source, skipped tasks, cache policy và inputs khác. Đối với **ý định chạy lại tests**, --rerun-tasks hoặc --rerun trên task cụ thể rõ nghĩa hơn clean.

## 5. Bài lab Java 17 và JUnit 5: ba lượt chạy, ba kết quả khác nhau

Bài lab độc lập, dùng **Gradle Groovy DSL + Java 17 + JUnit Jupiter 5**. Nó tạo **hai test cases**, mỗi case in một marker chỉ khi test method thực thi. Chúng ta sẽ dùng task outcome để biết marker đó thuộc lượt chạy hiện tại hay chỉ tồn tại trong report cũ.

### 5.1. Yêu cầu và cấu trúc

Cần:
- JDK 17 hoặc Java 17 toolchain có sẵn hoặc được provision.
- Gradle Wrapper tương thích với JDK 17.
- Kết nối Maven Central khi cache chưa có JUnit libraries.
- Không cần database, Docker hay external API.

~~~text
gradle-test-cache-lab/
├── settings.gradle
├── build.gradle
├── gradlew                      # được tạo bằng Gradle Wrapper
├── gradlew.bat
├── gradle/wrapper/...
└── src/
    ├── main/java/demo/Calculator.java
    └── test/java/demo/CalculatorTest.java
~~~

Nếu chưa có Wrapper, dùng một Gradle đã cài tương thích chạy **gradle wrapper** từ project root, sau đó sử dụng ./gradlew hoặc .\gradlew.bat.

### 5.2. settings.gradle

~~~groovy
rootProject.name = 'gradle-test-cache-lab'
~~~

Không cần pluginManagement hoặc một subproject khác cho bài lab, vì java là core plugin và JUnit là test library trên dependency classpath, không phải Gradle plugin cần resolve bằng plugins DSL.

### 5.3. build.gradle hoàn chỉnh

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

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

dependencies {
    // Đồng bộ version giữa JUnit Jupiter và JUnit Platform.
    testImplementation platform('org.junit:junit-bom:5.10.2')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    testLogging {
        // Log events chỉ được tạo khi test framework chạy thật.
        events 'started', 'passed', 'skipped', 'failed'
        showStandardStreams = true
        exceptionFormat 'full'
    }
}
~~~

**Đọc từng phần:**
- id 'java' tự tạo sourceSet test và task test kiểu Test.
- testImplementation dùng **JUnit BOM 5.10.2** để đồng bộ JUnit components.
- junit-jupiter cung cấp API/engine JUnit Jupiter qua dependencies.
- junit-platform-launcher có trong testRuntimeClasspath để Gradle chạy JUnit Platform.
- useJUnitPlatform() bật JUnit Platform cho task.
- testLogging.events và showStandardStreams đưa **test event/console output mới** lên Gradle console khi tests thực thi.
- Không đặt options hoặc callback tạo random seed/time nhằm đảm bảo bài lab deterministic.
- **Build cache bật/tắt bằng CLI** trong từng phép thử; build.gradle không ép org.gradle.caching=true.

**Lưu ý phiên bản:** JUnit 5.10.2 là một version phát hành thực, phù hợp cho ví dụ. Nếu tổ chức đã chuẩn hóa JUnit phiên bản khác, hãy dùng BOM/version tương ứng và kiểm thử. Không trộn JUnit Jupiter mới với JUnit Platform launcher cũ mà không có lý do.

### 5.4. Code ứng dụng: Calculator.java

**src/main/java/demo/Calculator.java**

~~~java
package demo;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int left, int right) {
        return Math.addExact(left, right);
    }

    public static String label(int value) {
        return "v=" + value;
    }
}
~~~

Mã dùng Java 17 hợp lệ, không có truy cập external services. Math.addExact(int,int) thuộc JDK và có thể ném ArithmeticException nếu overflow; với input 2 và 3 không có overflow.

### 5.5. Hai bài kiểm thử: CalculatorTest.java

**src/test/java/demo/CalculatorTest.java**

~~~java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {

    @Test
    void addsTwoNumbers() {
        System.out.println("TEST_EXECUTED=addsTwoNumbers");
        assertEquals(5, Calculator.add(2, 3));
    }

    @Test
    void labelsNumber() {
        System.out.println("TEST_EXECUTED=labelsNumber");
        assertEquals("v=5", Calculator.label(5));
    }
}
~~~

Trong một **lần thực thi JUnit thật**, hai marker sau do test methods in ra:

~~~text
TEST_EXECUTED=addsTwoNumbers
TEST_EXECUTED=labelsNumber
~~~

**Thứ tự không được bảo đảm**; JUnit 5 có thứ tự test method riêng, và một số cấu hình parallelism có thể làm output interleave. Mỗi marker là bằng chứng **bên trong lần test execution tạo ra nó**, nhưng marker cũng có thể tồn tại trong file report/cache sau này. Do đó đừng mở XML cũ rồi coi marker trong XML là bằng chứng tests vừa chạy hôm nay.

JUnit assertions được viết cố định:
- add(2,3) trả 5.
- label(5) trả "v=5".
- Cả hai test cases pass nếu Calculator.java đúng như trên.

### 5.6. Lượt 1 — build baseline và tạo cache entry

Chạy từ project root trên Linux/macOS:

~~~bash
./gradlew clean test --build-cache --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test --build-cache --console=plain
~~~

Mục tiêu:
1. Xóa outputs cũ của project.
2. Compile Java source và test classes.
3. Thực thi task test bằng JUnit Platform.
4. Với build cache được bật, Gradle **có thể lưu** outputs của cacheable tasks nếu đủ điều kiện.

Nếu cache trước đó đã có một entry hoàn toàn tương thích, **ngay ở lượt 1** task vẫn có thể **FROM-CACHE**, không thực thi tests. Bởi vậy muốn chứng minh lượt 1 thực thi thật, phải **đọc task :test outcome**; nếu là FROM-CACHE, chuyển sang lệnh ép run dưới đây để tạo một lượt thực sự.

Câu lệnh đảm bảo bỏ qua normal cache/up-to-date shortcuts để có lượt thực thi tạo baseline:

~~~bash
./gradlew test --rerun-tasks --build-cache --console=plain
~~~

Với test sources/classpath hợp lệ và không có skip/dry-run, Gradle sẽ thực thi test methods. Vì --build-cache bật, kết quả thực thi có thể được lưu vào build cache theo điều kiện cacheability. Tuy nhiên, **không bảo đảm mọi cache policy đều cho phép lưu**, nên phần lượt FROM-CACHE cần kiểm tra outcome chứ không đoán.

Ở lần test thực thi, console có testLogging events và các marker:
- TEST_EXECUTED=addsTwoNumbers
- TEST_EXECUTED=labelsNumber

**Không khẳng định toàn bộ log Task :compileJava hoặc Task :test có thứ tự/định dạng giống nhau trên mọi Gradle/JDK.**

### 5.7. Lượt 2 — chạy không sửa gì, thường UP-TO-DATE

~~~bash
./gradlew test --build-cache --console=plain
~~~

Nếu không có inputs/outputs thay đổi và lượt trước thành công:

~~~text
> Task :test UP-TO-DATE
~~~

Ở lượt này **không có lần gọi mới tới CalculatorTest.addsTwoNumbers hoặc labelsNumber**. Hai marker test method không được in bởi một JUnit process mới; nếu bạn vẫn tìm thấy marker trong XML/HTML từ lượt trước, đó là **dữ liệu được lưu lại**.

**Chẩn đoán đúng:** UP-TO-DATE không có nghĩa Test task bị Gradle bỏ sót. Nó cho biết Gradle đã tối ưu bằng cách dùng trạng thái output local, phù hợp với input mà Gradle đã theo dõi.

### 5.8. Lượt 3 — xóa outputs nhưng có thể FROM-CACHE

~~~bash
./gradlew clean test --build-cache --console=plain
~~~

Nếu trước đó Gradle đã lưu một cache entry cho cùng test inputs, bạn có thể thấy:

~~~text
> Task :test FROM-CACHE
~~~

Đây là **cache hit**. Gradle phục hồi test outputs — bao gồm các kết quả dùng để tạo/hiển thị test reports — mà **không chạy JUnit methods trong lần invocation hiện tại**.

Nếu thay vào đó thấy:

~~~text
> Task :test
~~~

thì có thể là **cache miss** hoặc cache policy không cho tái sử dụng, và task đã thực thi thật. Điều đó không làm bài lab sai; chính sự khác nhau của task outcome là điều cần quan sát.

Các lý do cache miss có thể gồm:
- Không có cache entry tương ứng.
- Build cache không thực sự bật hoặc policy không cho đọc/write.
- Input fingerprint đổi (JDK/toolchain/test classes/runtime dependencies/JVM options).
- Task/plugin có cấu hình không cacheable.
- Cache entry bị xóa/evicted hoặc không tương thích với môi trường.
- Test task có inputs chứa thông tin không relocatable theo cấu hình đang dùng.

**Không ép bài thực hành phải xuất FROM-CACHE bằng cách tự giả mạo log.** Khi một cache hit chưa xuất hiện, hãy nêu thực tế là cache miss và kiểm tra logs.

### 5.9. Lượt 4 — buộc kiểm thử thực sự chạy lại

~~~bash
./gradlew test --rerun-tasks --no-build-cache --console=plain
~~~

Kỳ vọng:
- :test không UP-TO-DATE.
- :test không FROM-CACHE.
- JUnit Platform chạy hai test methods nếu không có điều kiện skip/dry-run.
- Console có sự kiện passed và hai marker in **trong invocation hiện tại**.
- Assertions pass; BUILD SUCCESSFUL.

Đây là cách trả lời yêu cầu **“Tôi muốn chạy lại test bây giờ, không dùng kết quả cũ”**. Có thể thay bằng --rerun của task test nếu Gradle version hỗ trợ; ưu điểm là không buộc các task dependencies compile lại cùng lúc.

**Vấn đề chi phí:** --rerun-tasks có thể buộc compileJava/compileTestJava và tasks liên quan chạy lại, không chỉ test. Trên repo lớn, hãy cân nhắc --rerun task option, chia riêng unit/integration suite hoặc cơ chế CI thích hợp. Đừng đánh đổi thời gian vô điều kiện khi một cache hit hợp lệ đã đáp ứng mục tiêu.

### 5.10. Bảng các lượt chạy

| Lượt | Câu lệnh (điểm khác chính) | :test outcome thường thấy | JUnit methods chạy trong lượt đó? |
|---|---|---|---|
| 1 | clean test --build-cache | Executed khi cache miss; có thể FROM-CACHE nếu entry đã tồn tại | Chỉ khi executed |
| 1b | test --rerun-tasks --build-cache | Executed | Có, nếu tests được chọn |
| 2 | test --build-cache, không đổi inputs | UP-TO-DATE | Không |
| 3 | clean test --build-cache | FROM-CACHE nếu key khớp/entry có; nếu không thì executed | Không khi FROM-CACHE; có khi executed |
| 4 | test --rerun-tasks --no-build-cache | Executed | Có, nếu tests được chọn |

**Cần nhớ:** Sự khác biệt được kiểm tra ở **mỗi invocation cụ thể**. Không có một câu “./gradlew test luôn chạy tests” hoặc “build cache luôn có hit” áp dụng cho mọi project.

## 6. Lệnh phân tích test results và xác nhận execution

### 6.1. Xem Gradle Test task và các test events

~~~bash
./gradlew test --console=plain --info
~~~

Log --info có thể giúp:
- Giải thích task UP-TO-DATE hay cache miss.
- Hiển thị test worker execution khi thực sự chạy.
- Cho biết selected test framework/task details theo Gradle version.

**Không phụ thuộc tuyệt đối vào một chuỗi log cụ thể** như "Starting process 'Gradle Test Executor ...'" vì output thay đổi theo Gradle version, test framework và log level. Hãy dùng task outcome và testLogging.events để có bằng chứng kết hợp.

Nếu cần ép một lượt test có logs mới:

~~~bash
./gradlew test --rerun-tasks --no-build-cache --console=plain --info
~~~

### 6.2. Test reports

Gradle Java Test task thường xuất:

~~~text
build/reports/tests/test/index.html
build/test-results/test/TEST-demo.CalculatorTest.xml
build/test-results/test/binary/...
~~~

Khi có hai test cases pass, XML có thể chứa một testcase entry cho mỗi method và test suite counts tương ứng. Dùng report để biết **tests nào pass/fail/skipped**; dùng **task outcome** để biết report đó có được sinh ra bởi test execution mới hay có thể được reuse.

Ví dụ nội dung **rút gọn để minh họa**, không phải XML nguyên văn do mọi JUnit/Gradle version sinh ra:

~~~xml
<testsuite name="demo.CalculatorTest" tests="2" failures="0" errors="0">
  <testcase classname="demo.CalculatorTest" name="addsTwoNumbers()"/>
  <testcase classname="demo.CalculatorTest" name="labelsNumber()"/>
</testsuite>
~~~

**Cẩn thận:** Không dùng một XML report có tests="2" làm bằng chứng chắc chắn “hai tests chạy hôm nay”. Nếu FROM-CACHE, file XML vẫn có thể tồn tại và mang số liệu này.

### 6.3. Phải kết hợp hai trục bằng chứng

Một kết luận đáng tin gồm:

1. **Task :test không UP-TO-DATE/FROM-CACHE/SKIPPED/NO-SOURCE.**
2. Invocation **không** dùng --dry-run hoặc --test-dry-run.
3. Test execution thực sự được framework khởi chạy.
4. Có **test events/results mới** từ invocation (started/passed/failed).
5. Số test cases được chọn >0 và khớp phạm vi yêu cầu.
6. CI/repository đúng branch, commit, JDK, task path và test framework.
7. Không có test filter vô tình loại phần lớn test suite.

Nếu yêu cầu chỉ là **kiểm tra build đã có kết quả test hợp lệ với inputs**, một cache hit có thể đủ. Nếu yêu cầu là **kiểm tra một môi trường sống ở thời điểm hiện tại**, thì phải ép thực thi và thiết kế test phù hợp với external state.

### 6.4. Timestamp không phải bằng chứng duy nhất

Thời gian sửa file XML có thể thay đổi khi cache restore/copy; một report có timestamp mới không chứng minh JUnit @Test được gọi lại. Ngược lại, report có timestamp cũ vẫn có thể là output của build hợp lệ.

**Nguồn chứng cứ mạnh hơn:** Task execution outcome + test framework events trong invocation + logs/report provenance. Khi có Build Scan/Develocity được phép, có thể kiểm tra task execution/cache outcomes trên giao diện phân tích build.

## 7. Test filtering và dry-run: task chạy nhưng tests có thực sự chạy?

### 7.1. Chỉ chạy một test case bằng --tests

~~~bash
./gradlew test --tests "demo.CalculatorTest.addsTwoNumbers" --rerun-tasks --no-build-cache
~~~

Với JUnit Platform và test class/method đúng như lab, command chỉ chọn **addsTwoNumbers**. Marker còn lại labelsNumber **không được in bởi test method mới** trong lượt đó.

Nếu lệnh không chọn đúng test (sai tên package, mismatch pattern hoặc phương thức không còn tồn tại), Gradle có thể báo **No tests found for given includes**, trừ khi build/plugin cấu hình cách xử lý khác.

**Không kết luận “toàn bộ suite pass”** khi chỉ chạy một test qua --tests. Cần kiểm tra pattern/filters trong CI, không chỉ task outcome.

### 7.2. --test-dry-run

Gradle hỗ trợ test dry-run để mô phỏng test selection:

~~~bash
./gradlew test --test-dry-run
~~~

Mục đích là biết test cases nào **sẽ được chọn**; phương thức @Test **không được thực thi thực sự**. Gradle có thể tạo reports cho các tests được chọn theo chế độ mô phỏng. Không dùng kết quả ấy làm một lượt verification thật.

### 7.3. --dry-run (Gradle task dry run)

~~~bash
./gradlew test --dry-run
~~~

Gradle liệt kê task graph nhưng **không thực thi task actions**. Nó không chứng minh tests đã chạy. Đừng nhầm --dry-run (task execution simulation) với --test-dry-run (mô phỏng test execution/selection của Test task).

### 7.4. @Disabled, assumptions và skipped test cases

JUnit Jupiter có thể dùng:

~~~java
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;

class ExampleTest {
    @Disabled("Chưa có môi trường test")
    @Test
    void notExecuted() {
        throw new AssertionError("Should not run");
    }
}
~~~

Đây là **snippet minh họa**, không phải file thứ ba của lab. Nếu Test task được thực thi và một method bị @Disabled, method đó không được gọi; Gradle report có thể đánh dấu test case **skipped**, trong khi task :test vẫn executed và các test cases khác vẫn pass.

Phân biệt:
- **Task skipped**: cả Test task không chạy.
- **Test skipped**: JUnit framework bỏ qua một hoặc nhiều cases.
- **Task FROM-CACHE**: JUnit framework không chạy mới, dù report có thể chứa skipped case cũ.

### 7.5. Task enabled/onlyIf và -x test

Trong build.gradle có thể có:

~~~groovy
tasks.named('test', Test) {
    onlyIf {
        !project.hasProperty('skipTests')
    }
}
~~~

Đây là **snippet minh họa**; khi chạy -PskipTests, task có thể SKIPPED dù dùng --rerun-tasks. Nếu build dùng **test.enabled = false** hoặc lệnh **-x test**, việc ép rerun cũng không làm tests tự chạy.

**Không đưa snippet onlyIf trên vào lab gốc nếu bạn muốn chứng minh rerun tests**, vì nó tạo thêm điều kiện skip và có thể gây hiểu nhầm.

## 8. Tại sao build cache an toàn cho unit tests nhưng cần cảnh giác với integration tests?

### 8.1. Unit tests deterministic

Ví dụ lab CalculatorTest:
- Đầu vào luôn là 2,3 và 5.
- Không gọi network/DB.
- Không phụ thuộc đồng hồ hay random seed không cố định.
- Không ghi file ngoài task outputs.
- Cùng code/classpath/test runner tạo cùng kết quả.

Một cache hit có thể có ý nghĩa: **những test cases deterministic này đã được xác thực trước đó với inputs tương đương**, và cache result đã được lưu. Gradle có thể tránh chạy lại để tiết kiệm CI time.

Tuy nhiên, kiểm thử cần đánh giá:
- Mức độ đáng tin của shared cache.
- Chính sách bắt buộc chạy lại trước release.
- Các input môi trường có được Gradle biết hay không.
- Có bị test flakiness che giấu bởi cached success không.

### 8.2. Integration tests phụ thuộc trạng thái bên ngoài

Ví dụ integration test:
- Gọi API staging và kiểm tra availability.
- Truy cập database đang có dữ liệu thay đổi.
- Gửi message tới queue.
- Kiểm tra chứng chỉ sắp hết hạn.
- Đọc external service feature flag.
- Kiểm tra throughput/performance theo thời điểm.

Dù Java source **không đổi**, kết quả đúng có thể **đổi** theo external state. Nếu Test task output được cached từ hôm qua, CI hôm nay có thể nhận FROM-CACHE và **không kiểm tra staging mới**.

Do đó, phải quyết định rõ:
- Mục tiêu là **xác nhận deterministic code behavior**? Cache có thể phù hợp.
- Mục tiêu là **đo trạng thái external system hiện tại**? Thường cần rerun thật.
- Cần đánh dấu external state thành inputs? Chỉ khi có cách mô hình hóa đáng tin, không rò secrets và không làm cache key dễ biến động vô ích.

### 8.3. Time-dependent tests

~~~java
@Test
void currentHourIsMorning() {
    int hour = java.time.LocalTime.now().getHour();
    org.junit.jupiter.api.Assertions.assertTrue(hour < 12);
}
~~~

Đây là **anti-example** minh họa vì sao test phụ thuộc giờ thực có thể thay kết quả mà Gradle không thấy source/test inputs thay đổi. Đừng đưa loại test này vào suite deterministic. Cách tốt hơn là **inject Clock** hoặc một thời gian cố định vào code dưới test:

~~~java
java.time.Clock fixed = java.time.Clock.fixed(
        java.time.Instant.parse("2026-01-01T08:00:00Z"),
        java.time.ZoneOffset.UTC
);
~~~

Khi code nhận Clock như dependency, unit test có thể kiểm chứng logic ở một thời điểm xác định và ổn định. Nếu mục tiêu thật là kiểm tra thời gian thực, dùng integration/monitoring task có chính sách rerun phù hợp.

### 8.4. Randomness và concurrency

Một test random không seed có thể fail không ổn định. Cache hit cho một lần PASS cũ không phát hiện flakiness mới. Với unit/property tests, dùng seed cố định hoặc log seed có thể tái hiện. Với stress/concurrency tests, cần phân biệt mục tiêu **độ ổn định qua nhiều lượt chạy** và **kiểm chứng deterministic output**.

Nếu muốn tìm flaky behavior, chủ động rerun nhiều lần theo policy, không dùng cache hit làm dữ liệu giả cho số lượt thử.

### 8.5. Environment và secrets

Test có thể đọc System.getenv("API_TOKEN") hoặc environment variables khác ngay trong test worker process. Không mặc định Gradle ghi mọi environment variable mà test đọc vào cache key; nhiều yếu tố external không được mô hình hóa thành task input.

Đừng in token/secret ra test logs chỉ để chứng minh chúng thay đổi. Nếu test phải dùng credentials, dùng CI secret storage, tách integration suite và cân nhắc policy không cache/luôn rerun với external service.

## 9. Chính sách ép chạy lại cho một Test task

### 9.1. Cách đơn giản nhất: CLI theo nhu cầu

Cho một lần chạy lại:

~~~bash
./gradlew test --rerun-tasks --no-build-cache --console=plain
~~~

Cho một lần chạy lại chỉ Task :test trên phiên bản hỗ trợ task --rerun:

~~~bash
./gradlew test --rerun --no-build-cache --console=plain
~~~

**Ưu điểm:** Không phải sửa build script thường xuyên chỉ để điều tra một lần; ý định rõ ràng trong CI log/command history.

### 9.2. Không cache một loại test có external state

Nếu mọi lần chạy **integrationTest** phải kiểm tra service đang sống, bạn có thể chủ động tắt caching của riêng task đó:

~~~groovy
tasks.named('integrationTest', Test) {
    outputs.doNotCacheIf(
        'Integration tests phụ thuộc dịch vụ ngoài thay đổi'
    ) {
        true
    }
}
~~~

Đây là **snippet dành cho project đã đăng ký task integrationTest kiểu Test**, không thể chạy nguyên trong project chỉ có test task mặc định.

**Quan trọng:** Tắt **build cache** cho task **không tự tắt up-to-date checks**. Nếu muốn task luôn thực thi khi được yêu cầu, cần xử lý cả hai cơ chế, ví dụ:

~~~groovy
tasks.named('integrationTest', Test) {
    outputs.doNotCacheIf(
        'Phải kiểm tra trạng thái môi trường đang chạy'
    ) {
        true
    }

    outputs.upToDateWhen {
        false
    }
}
~~~

Cách này buộc task không được xem là up-to-date, đồng thời không dùng build cache cho task. Chỉ áp dụng với suites **thực sự có yêu cầu luôn chạy**; nếu áp rộng lên unit tests, bạn sẽ đánh mất nhiều tối ưu hợp lý. Và vẫn cần đảm bảo task có test classes, không bị disabled/onlyIf false/dry-run.

### 9.3. Custom integrationTest task là một task khác test

Trong build có source set integrationTest được đăng ký đúng, task có thể tên **integrationTest** thay vì **test**. Nếu chạy:

~~~bash
./gradlew test --rerun-tasks
~~~

đó là **unit-test task path**, không có nghĩa custom integrationTest cũng nằm trong task graph. Bạn cần chạy đúng task:

~~~bash
./gradlew integrationTest --rerun-tasks --no-build-cache
~~~

Hoặc tạo lifecycle dependency rõ ràng theo CI policy. Không dùng đường dẫn chung trong mọi repo nếu chúng có cách tổ chức test source sets khác nhau.

### 9.4. Nếu CI cần cả cached và fresh suite

Một hướng thiết kế:

1. **Unit tests deterministic** chạy thường xuyên và cho phép build cache.
2. **Integration tests/live smoke tests** có task riêng, thực thi với chính sách không reuse kết quả cũ.
3. **Release gate** chạy lại các nhóm test bắt buộc bằng cờ hoặc task policy tương ứng.
4. CI lưu **task outcomes** và **test reports**, để người review biết pass được tính từ cache hay fresh run.
5. Khi kết quả fail, thu thập diagnostics/stacktraces; không bật cache để “làm xanh” lỗi.

Phân tách rõ ràng giúp tối ưu build time mà vẫn bảo đảm các kiểm tra cần tính tươi mới được thực thi.

## 10. Khi nào một cache hit thực sự được coi là hợp lệ?

Một cache hit chỉ có ý nghĩa nếu:
- Test task được Gradle model hóa với inputs/outputs đúng.
- Tests deterministic hoặc mọi yếu tố ảnh hưởng kết quả được biểu diễn thành inputs phù hợp.
- Cache entry đến từ nguồn tin cậy theo chính sách tổ chức.
- Cùng cache key thật sự biểu thị cùng task behavior.
- Kết quả trước đó thành công và phù hợp với cách nhóm đánh giá tests.
- Không có yêu cầu bắt buộc chạy lại vào thời điểm hiện tại.

**Cache hit không phải gian lận.** Gradle được thiết kế để tránh những công việc lặp lại không cần thiết. Nhưng **cache hit không phải phép đo mới**; mọi báo cáo QA/CI phải mô tả đúng điều này.

### 10.1. Task output cache không phải một bảng kết quả test vĩnh viễn

Test failures/worker crashes không nên được “coi như thành công” từ cache. Gradle task output cache phục vụ những **outputs hợp lệ** và kiểm tra inputs; khi source/test behavior thay đổi ở input được theo dõi, cache key thay đổi và một cache hit không còn phù hợp.

Tuy nhiên, khi **external state không được mô hình hóa**, một cached PASS có thể che một lỗi môi trường mới. Đó là lý do integration/live tests cần policy khác.

### 10.2. Remote cache và QA gate

Khi team dùng remote cache, test output của người khác/CI job khác có thể được dùng nếu Gradle xác định key phù hợp. Nếu yêu cầu kiểm toán là “commit này đã có kết quả test hợp lệ từ môi trường được tin cậy”, có thể chấp nhận với policy rõ. Nếu yêu cầu là “runner hiện tại đã thực sự gọi database staging”, cache hit **không đạt**.

Đừng lấy cache result từ nguồn không đáng tin cho quy trình release quan trọng. Quản lý remote cache endpoints, quyền ghi/đọc, plugin versions và khả năng xác minh artifact/result theo chính sách supply chain.

### 10.3. Build cache khác test retry

**Test retry** chạy lại một test case thất bại theo plugin/framework/policy để phân biệt flaky failures. **Build cache** không phải cơ chế retry: nó có thể **không chạy test case** và chỉ phục hồi kết quả PASS cũ.

Cả hai có thể cùng có trong pipeline nhưng ý nghĩa thống kê khác nhau:
- "Test retried twice" có nghĩa có thêm lượt test execution thật.
- "Test FROM-CACHE" có nghĩa không có test execution mới trong lượt build ấy.

Không đưa cache hit vào số lần “đã chạy lại để xác minh flakiness”.

## 11. Xem log mà không tạo kết luận giả

### 11.1. Một đoạn build log đúng cách đọc

~~~text
> Task :compileJava UP-TO-DATE
> Task :compileTestJava UP-TO-DATE
> Task :test FROM-CACHE

BUILD SUCCESSFUL
~~~

**Kết luận được phép:** Task :test không gọi lại framework trong lượt này; kết quả test được khôi phục. Có thể dùng report để thấy chúng từng pass.

**Kết luận không được phép:** "Hai test methods vừa chạy lại và pass hôm nay."

### 11.2. Log task thực thi thật

~~~text
> Task :test
CalculatorTest > addsTwoNumbers() PASSED
CalculatorTest > labelsNumber() PASSED
~~~

**Ví dụ minh họa**: testLogging format, cách Gradle nhóm console output và tên display của JUnit có thể thay đổi. Khi task executed và test events hiện diện trong **invocation hiện tại**, có cơ sở kết luận tests đã được chạy thật.

Nếu bật showStandardStreams, có thể xem cả marker từ @Test. Nhưng **nếu bạn chỉ đọc log đã lưu từ invocation cũ**, marker không chứng minh lượt mới.

### 11.3. Task outcomes trong build scan

Trong môi trường có Gradle Build Scan/Develocity và được phép gửi metadata:
- Xem từng task :test, :integrationTest, :app:test.
- Xem outcome executed/up-to-date/from-cache.
- Xem cache keys/cache hits/misses theo khả năng phiên bản.
- So sánh test reports và performance.
- Xem thông tin provenance/CI runner.

Không cần cài plugin ngoài chỉ để hoàn thành bài lab; **--console=plain --info** đủ để học nguyên lý.

### 11.4. Đừng gộp toàn bộ multi-project test tasks

Trong multi-project:

~~~text
:core:test UP-TO-DATE
:api:test FROM-CACHE
:app:test
:integration:test SKIPPED
~~~

Đây là bốn outcomes **khác nhau**, không thể gộp thành câu “all tests rerun”. Hãy báo cáo **theo task path** và số test cases executed ở từng task; task :app:test có thể thực thi trong khi các task khác chỉ reuse hoặc skip.

## 12. Các lỗi thường gặp và cách xử lý

### Lỗi 1 — “BUILD SUCCESSFUL” nên chắc chắn mọi test đã chạy

**Sai.** UP-TO-DATE/FROM-CACHE cho kết quả thành công mà không có test execution mới.

**Cách sửa:** Đọc task outcome và xác minh test events cho invocation hiện tại. Khi cần fresh run, dùng --rerun-tasks/--rerun và đảm bảo tests không bị skip/dry-run.

### Lỗi 2 — Thêm --no-build-cache nhưng test vẫn UP-TO-DATE

**Nguyên nhân:** --no-build-cache chỉ tắt build cache, không tắt up-to-date checks.

**Cách sửa:** Dùng --rerun-tasks hoặc task --rerun khi cần thực thi lại. Không cần xóa ~/.gradle/caches bằng tay.

### Lỗi 3 — clean test --build-cache vẫn FROM-CACHE

**Nguyên nhân:** clean xóa build outputs local nhưng build cache có kết quả tương thích.

**Cách sửa:** Nếu muốn tests chạy thật, dùng --rerun-tasks hoặc clean test --no-build-cache. Nếu muốn tận dụng cache thì FROM-CACHE là hành vi đúng.

### Lỗi 4 — Thấy XML tests=2 rồi ghi báo cáo “đã chạy lại hai tests”

**Nguyên nhân:** XML có thể là task output được phục hồi từ cache hoặc còn từ lần trước.

**Cách sửa:** Kết hợp task outcome + test events của invocation hiện tại. XML phản ánh kết quả, không tự phản ánh thời điểm JUnit đã chạy.

### Lỗi 5 — Test task executed nhưng không có marker

**Nguyên nhân có thể:** Test logging ở mức không hiện standard streams; test filter loại case; test class không được phát hiện; JUnit engine/launcher thiếu; --test-dry-run; method bị @Disabled hoặc task failed trước khi tests chạy.

**Cách sửa:** Kiểm tra testLogging.showStandardStreams, --tests patterns, reports, framework deps và build arguments; đừng vội kết luận cached nếu task không FROM-CACHE.

### Lỗi 6 — Test task NO-SOURCE

**Nguyên nhân:** Không có compiled tests phù hợp cho task, source set/path sai hoặc test code chưa được compile.

**Cách sửa:** Kiểm tra src/test/java, Java plugin, :compileTestJava, testClassesDirs và testClasspath. NO-SOURCE không phải cache hit.

### Lỗi 7 — Tests bị SKIPPED mặc dù --rerun-tasks

**Nguyên nhân:** task disabled, onlyIf false, -x test hoặc custom điều kiện. --rerun-tasks không bỏ các điều kiện này.

**Cách sửa:** Xác định và sửa lý do skip. Đừng dựa vào --rerun-tasks như cách cưỡng ép mọi task bất chấp cấu hình.

### Lỗi 8 — Chạy --tests rồi công bố toàn bộ suite PASS

**Nguyên nhân:** Filter chỉ chọn một class/method.

**Cách sửa:** Chạy full suite khi gate yêu cầu, đọc report số tests và logs pattern. --tests có ích để debug nhưng không phải bằng chứng toàn suite.

### Lỗi 9 — CI integration test hôm nay PASS dù staging đang hỏng

**Nguyên nhân có thể:** Integration task được phục hồi từ cache hoặc UP-TO-DATE vì external state không nằm trong inputs.

**Cách sửa:** Tách live integration suite, tắt cache/up-to-date hoặc rerun chủ động, đồng thời thiết kế observability và môi trường test đáng tin.

### Lỗi 10 — --rerun-tasks rất chậm

**Nguyên nhân:** Cờ ép **mọi task trong selected graph**, không chỉ test.

**Cách sửa:** Dùng task-specific --rerun nếu phiên bản hỗ trợ hoặc tổ chức tasks/pipeline riêng. Chỉ rerun khi thật sự cần, để unit tests tận dụng cache hợp lệ.

### Lỗi 11 — Task FROM-CACHE nhưng remote cache đã bị xóa

**Tình huống:** Một cache hit còn có thể lấy từ **local cache** dù remote cache không có entry. Tên FROM-CACHE không chỉ nguồn cụ thể.

**Cách sửa:** Kiểm tra cache configuration/logs, đừng suy luận nguồn hit từ mỗi nhãn task.

### Lỗi 12 — Lần đầu chạy lab đã FROM-CACHE

**Nguyên nhân:** Cache entry phù hợp có sẵn từ build/runner khác, hoặc cùng workspace từng chạy task đó.

**Cách sửa:** Dùng --rerun-tasks --no-build-cache để tạo một lượt execution thật. Bài lab không yêu cầu giả mạo một cache miss.

### Lỗi 13 — JUnit test fails nhưng Gradle vẫn báo cached PASS

**Nguyên nhân cần điều tra:** External state đã đổi nhưng không nằm trong declared inputs, test code/classpath thực tế không đổi, hoặc CI đang đọc report của task/commit khác.

**Cách sửa:** Rerun thật trên đúng code/environment, kiểm tra task path và inputs; sau đó tách tests không deterministic ra khỏi caching policy.

### Lỗi 14 — Configuration cache reuse bị hiểu thành test reuse

**Nguyên nhân:** Dòng "Reusing configuration cache" thuộc **configuration phase**, không phải Test task output cache.

**Cách sửa:** Quan sát **:test outcome** riêng. Configuration cache hit vẫn có thể đi cùng Test task executed hoặc UP-TO-DATE/FROM-CACHE.

### Lỗi 15 — Đổi README nhưng :test không chạy lại

**Nguyên nhân:** README thường không phải input của Java Test task.

**Cách sửa:** Đây là tối ưu hợp lý nếu tests không phụ thuộc README. Nếu test thật sự đọc file ấy, khai báo nó thành task input hoặc đổi kiến trúc để tránh dependency ẩn.

### Lỗi 16 — Thay một environment variable mà cache key không đổi

**Nguyên nhân:** Test process đọc biến môi trường mà task/plugin không khai báo theo cách Gradle theo dõi.

**Cách sửa:** Khai báo input đúng khi biến thực sự quyết định deterministic test output, không log secrets; với biến phụ thuộc external live state, cân nhắc không cache và rerun.

### Lỗi 17 — Test reports được khôi phục nhưng timestamp mới

**Nguyên nhân:** Cache restore/copy có thể ảnh hưởng metadata filesystem; timestamp không phải chứng cứ gọi @Test.

**Cách sửa:** Ưu tiên outcome và invocation log/test events.

### Lỗi 18 — Build cache bật nhưng không có FROM-CACHE

**Nguyên nhân có thể:** Task outputs vẫn up-to-date; chưa có entry; cache disabled/miss; inputs đổi; task bị loại khỏi caching.

**Cách sửa:** Nếu mục tiêu là quan sát cache hit, tạo entry bằng một execution cache-enabled, chạy clean và kiểm tra lại; nếu vẫn miss, dùng --info/build scan xem lý do. Không tự sửa console logs.

### Lỗi 19 — Task thực thi nhưng chỉ có test skipped

**Nguyên nhân:** @Disabled/assumptions/filters khiến test methods không được gọi, dù task có thể executed.

**Cách sửa:** Kiểm tra test counts: executed/passed/failed/skipped, những suite/engine được chọn và điều kiện test.

### Lỗi 20 — Bắt test mỗi lần bằng outputs.upToDateWhen { false } mà quên build cache

**Nguyên nhân:** Chỉ tắt up-to-date không tự thể hiện toàn bộ policy chống cache reuse.

**Cách sửa:** Khi yêu cầu không dùng cache, thêm outputs.doNotCacheIf(...) hoặc chạy --no-build-cache, và xác minh task luôn chạy thật theo đúng conditions. Tránh áp policy rộng lên deterministic unit tests.

## 13. Thiết kế CI report rõ ràng

Khi CI chạy nhiều nhóm tests, report nên bao gồm:

| Thông tin | Ví dụ | Tại sao quan trọng? |
|---|---|---|
| Git commit/branch | Commit đang kiểm tra | Xác định source dùng để build |
| Gradle Wrapper version | Phiên bản từ project | Task/CLI semantics có thể khác |
| Java toolchain/JVM | Java 17 | Test execution phụ thuộc JDK |
| Task path | :app:test, :api:test | Mỗi module có result/cache riêng |
| Task outcome | Executed / UP-TO-DATE / FROM-CACHE / SKIPPED | Phân biệt fresh run và reuse |
| Test filter | Full suite hoặc --tests pattern | Biết phạm vi cases thực thi |
| Number of tests | Passed/failed/skipped | Bằng chứng nội dung test report |
| Report provenance | Report thuộc invocation nào | Tránh đọc lại report cũ |
| Build cache policy | --build-cache / --no-build-cache | Giải thích khả năng cache |
| External environment | Staging version/service status | Chỉ có ý nghĩa với integration tests |
| Retry policy | Số lần rerun failed tests | Phân biệt flaky retry với cache reuse |

Cách mô tả chính xác:

- “**:app:test FROM-CACHE**; kết quả 24 tests được tái sử dụng, không có test execution mới trong job này.”
- “**:core:test UP-TO-DATE**; không cần chạy lại vì inputs/outputs local không đổi.”
- “**:integrationTest EXECUTED**; 8 tests chạy thật trong job hiện tại, 8 passed.”
- “**:api:test SKIPPED** do điều kiện môi trường, không tính là test execution.”

Tránh:
- “All tests rerun” khi có FROM-CACHE/UP-TO-DATE.
- “No tests happened anywhere” chỉ vì một task :test FROM-CACHE trong multi-project build.
- “Cache hit là lỗi” mà không xét mục tiêu pipeline.
- “Task executed nên full suite đã chạy” khi vẫn có --tests filter hoặc tests skipped.

## 14. Checklist điều tra nhanh theo tình huống

### Khi bạn hỏi “Tại sao test không chạy lại?”

1. Xác nhận lệnh **đúng project/task**: :app:test hay :core:test?
2. Xem :test outcome: UP-TO-DATE, FROM-CACHE, NO-SOURCE, SKIPPED hay executed?
3. Nếu UP-TO-DATE: inputs/outputs local chưa đổi; cân nhắc rerun theo mục tiêu.
4. Nếu FROM-CACHE: cache hit hợp lệ? Có external state khiến kết quả cũ không đủ không?
5. Nếu SKIPPED: kiểm tra onlyIf, enabled, -x, environment conditions.
6. Nếu NO-SOURCE: kiểm tra test source set, compiled classes và classpath.
7. Nếu executed nhưng test count = 0: xem filters, JUnit Platform/engine, discovery/dry-run.
8. Nếu cần fresh run: dùng --rerun-tasks --no-build-cache và xác minh test events.
9. Nếu đây là integration/live check: cân nhắc định nghĩa policy không reuse kết quả cũ.
10. Ghi rõ kết quả và phạm vi, đừng đổi toàn bộ build settings chỉ để điều tra một lần.

### Khi bạn hỏi “Cache có thật sự hoạt động không?”

1. Bật --build-cache hoặc org.gradle.caching=true.
2. Chạy một Test task deterministic thực sự và cacheable.
3. Xác minh build thành công và cache entry có thể được lưu.
4. Xóa build outputs hoặc thử trên workspace khác có cùng inputs.
5. Chạy lại với --build-cache.
6. Xem **:test FROM-CACHE** hay executed.
7. Nếu cache miss, dùng --info/Build Scan để tìm nguyên nhân.
8. Không suy luận cache hit chỉ từ “BUILD SUCCESSFUL”.
9. Không dùng external state biến động làm bài demo cache.
10. Không xóa/cấu hình lại toàn bộ Gradle User Home nếu không cần; điều đó có thể làm demo khó tái lập hơn.

### Khi bạn hỏi “Làm thế nào để bắt chạy test thật trong release?”

1. Xác định danh sách tasks bắt buộc: :app:test, :core:test, :integrationTest...
2. Quyết định suite nào được cache, suite nào phải fresh.
3. Trên tasks cần fresh, dùng --rerun-tasks hoặc task --rerun (nếu hỗ trợ), kiểm soát caching policy.
4. Đảm bảo tasks không SKIPPED/NO-SOURCE ngoài ý muốn.
5. Đảm bảo full suite, không vô tình --tests chỉ một test.
6. Lưu test events/reports và task outcomes trên CI.
7. Kiểm tra môi trường test thật, credentials và service readiness.
8. Tách retry policy khỏi cache policy.
9. Không đánh đổi coverage bằng skip tests để có build xanh.
10. Review logs trước khi phê duyệt release.

## 15. Bài tập tự kiểm tra

**Bài 1.** Gradle in > Task :test UP-TO-DATE rồi BUILD SUCCESSFUL. Có test method JUnit nào được gọi mới trong lượt đó không?

**Bài 2.** Gradle in > Task :test FROM-CACHE. Kết quả tests được lấy ở đâu và test worker JVM có chạy lại không?

**Bài 3.** Chạy ./gradlew test --no-build-cache lần hai khi inputs/outputs không đổi. Test có chắc chạy lại không?

**Bài 4.** Chạy ./gradlew clean test --build-cache. Vì sao có thể FROM-CACHE dù vừa clean?

**Bài 5.** Khi cần rerun tests thật, câu lệnh CLI có tính bảo đảm tốt hơn chỉ dùng --no-build-cache là gì?

**Bài 6.** --rerun-tasks và --rerun của riêng task test khác nhau thế nào?

**Bài 7.** Task :test không có outcome UP-TO-DATE/FROM-CACHE nhưng Gradle đang chạy --test-dry-run. Có được tính là lượt JUnit execution thật không?

**Bài 8.** Một report XML chứa tests="2" được khôi phục từ cache. Có thể viết “hai tests vừa chạy lại” không?

**Bài 9.** Unit test CalculatorTest chỉ dùng Math.addExact và literal input. Dùng build cache có thể hợp lý không? Vì sao?

**Bài 10.** Integration test gọi API staging. Source không đổi nhưng API đã lỗi hôm nay. Một cache hit từ hôm qua có đáp ứng mục tiêu kiểm tra staging hiện tại không?

**Bài 11.** Vì sao time-based test dùng LocalTime.now() có thể khiến cache result không phản ánh kết quả ở thời điểm mới?

**Bài 12.** Khi một test bị @Disabled, đó là Task SKIPPED hay test case skipped?

**Bài 13.** Chạy ./gradlew test --tests "demo.CalculatorTest.addsTwoNumbers" --rerun-tasks. Có thể báo full CalculatorTest suite đã chạy không?

**Bài 14.** Một Test task báo NO-SOURCE. Cần kiểm tra tối thiểu những đường dẫn/configuration nào?

**Bài 15.** Khi FROM-CACHE có thể đến từ local hoặc remote, có thể suy ra nguồn từ nhãn FROM-CACHE duy nhất không?

**Bài 16.** Configuration cache báo Reusing configuration cache. Điều đó có chứng minh Test task FROM-CACHE không?

**Bài 17.** Cách cấu hình một integrationTest task để không được cache và không UP-TO-DATE là gì?

**Bài 18.** Vì sao --rerun-tasks vẫn không chạy một Test task đang enabled=false?

**Bài 19.** Gradle có test events "passed" nhưng bạn không biết log thuộc invocation nào. Cần chứng cứ nào để khẳng định fresh execution?

**Bài 20.** Trong multi-project, :core:test UP-TO-DATE, :app:test FROM-CACHE, :integration:test executed. Bạn sẽ báo cáo thế nào cho chính xác?

### Gợi ý đáp án

1. **Không.** Task actions được bỏ qua do up-to-date check.
2. Outputs được phục hồi từ build cache phù hợp; **không chạy lại JUnit methods** trong invocation ấy.
3. **Không.** Up-to-date checks vẫn có thể cho UP-TO-DATE.
4. clean xóa local outputs nhưng không xóa cache entries; Gradle có thể phục hồi reports từ cache.
5. **./gradlew test --rerun-tasks --no-build-cache**, đồng thời kiểm tra task không bị skip/dry-run và test count >0.
6. **--rerun-tasks** ép selected task graph/tasks dependencies; **--rerun** (nếu hỗ trợ) ép task cụ thể, tránh rerun mọi dependency tasks.
7. **Không.** Test dry-run chỉ mô phỏng test selection/điều hành.
8. **Không.** XML là cached task output, không phải bằng chứng execution mới.
9. **Có.** Tests deterministic, cùng inputs cho cùng kết quả, nên reuse hợp lý nếu cache đáng tin.
10. **Không.** Mục tiêu live verification cần chạy thật với external state hiện tại.
11. Đồng hồ không nhất thiết là task input đã khai báo; test result có thể đổi mà cache key vẫn giống.
12. **Test case skipped** trong framework; cả Test task có thể vẫn executed.
13. **Không.** Chỉ một method được lọc chọn; không phải full suite.
14. src/test/java, compiled test classes, task testClassesDirs, useJUnitPlatform/test dependencies và test filters.
15. **Không.** Cần cache diagnostics/logs/Build Scan riêng.
16. **Không.** Configuration cache và task output cache là hai cơ chế khác.
17. Dùng **outputs.doNotCacheIf(...) { true }** và **outputs.upToDateWhen { false }** trên đúng Test task, vẫn kiểm tra điều kiện skip/dry-run.
18. --rerun-tasks không override task enabled/onlyIf conditions.
19. Task outcome, invocation identity/log, evidence test events được tạo trong lần chạy ấy, không chỉ report cũ.
20. Tách theo task: core không chạy mới (UP-TO-DATE), app khôi phục cache (FROM-CACHE), integration chạy thật; nêu test counts/failures của từng nhóm.

## Tài liệu chính thức

- [Gradle User Manual — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): Test task, useJUnitPlatform(), filtering, testLogging, XML/HTML reports, --test-dry-run.
- [Gradle User Manual — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): built-in Test cacheability, task output caching và cache key.
- [Gradle User Manual — Understanding Tasks](https://docs.gradle.org/current/userguide/more_about_tasks.html): UP-TO-DATE, FROM-CACHE và task outcomes.
- [Gradle User Manual — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): --build-cache, --no-build-cache, --rerun-tasks và task-specific --rerun.
- [Gradle User Manual — Gradle CLI Overview](https://docs.gradle.org/current/userguide/gradle_command_line.html): --dry-run, --test-dry-run, --tests và cách chọn tasks.
- [Gradle User Manual — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html): task inputs/outputs và up-to-date checks.
- [Gradle User Manual — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): cache giai đoạn cấu hình, không đồng nhất với test output cache.
- [Gradle User Manual — Adopting Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache_adoption.html): rerun task actions để kiểm tra execution-time behavior.
- [Gradle API — Test](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html): testClassesDirs, classpath, useJUnitPlatform(), testLogging, test filtering.
- [Gradle API — TaskOutputs](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/TaskOutputs.html): upToDateWhen và doNotCacheIf.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): JUnit Jupiter @Test, @Disabled, assertions, test lifecycle.

**Ghi nhớ:** **UP-TO-DATE** giữ kết quả task hợp lệ từ workspace, **FROM-CACHE** phục hồi kết quả task từ cache; **cả hai đều không phải một lượt chạy JUnit test methods mới**. **--no-build-cache** không tắt up-to-date checks, **clean --build-cache** vẫn có thể hit cache, còn **--rerun-tasks** (hoặc task --rerun nếu hỗ trợ) là công cụ ép Gradle xử lý lại tasks. Trước khi tuyên bố “tests đã chạy lại”, hãy kiểm tra **task outcome + test events mới + phạm vi tests thực sự được chọn**, và dùng chính sách không tái sử dụng cho những kiểm thử phụ thuộc trạng thái bên ngoài cần xác nhận tại thời điểm hiện tại.
# Thêm kiểm thử và cổng chất lượng với điều kiện thất bại rõ ràng

Một build đáng tin cậy cần trả lời được hai câu hỏi: **thay đổi này có hoạt động đúng không, và điều gì sẽ khiến pipeline từ chối nó?** Kiểm thử cung cấp bằng chứng về hành vi của phần mềm. Cổng chất lượng biến các tiêu chí đã thống nhất thành điều kiện pass/fail để lỗi được phát hiện trước khi merge hoặc phát hành.

Trong Gradle, không nên chỉ thêm một task test rồi coi như đã có quality gate. Cần tổ chức test theo phạm vi phù hợp, nối các bước kiểm tra vào lifecycle task, đặt ngưỡng rõ ràng cho coverage và static analysis, bảo đảm task thực sự chạy, đồng thời để build trả exit code khác 0 khi một điều kiện bắt buộc không đạt.

Ví dụ, một pipeline có thể yêu cầu:

- Unit tests phải pass.
- Integration tests phải pass trong môi trường test đã chuẩn bị.
- Coverage của phần code được đo phải đạt ngưỡng tối thiểu.
- Static analysis không có lỗi vượt chính sách.
- Formatting và cấu trúc source tuân thủ quy ước.
- Những task bắt buộc không được âm thầm bị skip hoặc bỏ qua lỗi.
- CI phải lưu báo cáo để người review biết test nào fail và vì sao.

Cổng chất lượng chỉ hữu ích khi tiêu chí có thể kiểm tra tự động, kết quả ổn định và thông báo thất bại đủ rõ để sửa.

## 1. Kiểm thử và quality gate giải quyết hai vấn đề khác nhau

Kiểm thử là hoạt động thực thi phần mềm với các tình huống đầu vào và xác nhận kết quả. Quality gate là tập điều kiện quyết định một thay đổi có được xem là đạt yêu cầu hay không.

Ví dụ:

- Unit test kiểm tra một hàm tính tổng trả về kết quả đúng.
- Integration test kiểm tra repository truy vấn đúng dữ liệu qua database test.
- Coverage verification kiểm tra tỷ lệ dòng được thực thi có đạt ngưỡng.
- Checkstyle kiểm tra quy tắc source code.
- Dependency/security scan kiểm tra dependency hoặc artifact theo policy.

Một test pass không đồng nghĩa code đã đủ chất lượng. Test có thể không bao phủ nhánh quan trọng, không kiểm tra trường hợp lỗi hoặc chỉ xác nhận rằng method không ném exception. Ngược lại, coverage cao không chứng minh assertion có ý nghĩa hoặc test đang kiểm tra hành vi đúng.

Quality gate cần kết hợp nhiều tín hiệu, mỗi tín hiệu trả lời một câu hỏi riêng. Tránh dùng một con số duy nhất như coverage để đại diện cho toàn bộ chất lượng.

### 1.1. Luồng tổng thể

~~~mermaid
flowchart TD
    A["Developer tạo thay đổi"] --> B["Compile và tạo artifact"]
    B --> C["Unit tests"]
    C --> D["Integration tests"]
    D --> E["Coverage verification"]
    E --> F["Static analysis và formatting"]
    F --> G["Các quality checks khác"]
    G --> H{"Tất cả gate bắt buộc đều đạt?"}
    H -->|Có| I["check/build thành công"]
    H -->|Không| J["Build thất bại, trả exit code khác 0"]
    J --> K["Xem report và sửa nguyên nhân"]
~~~

Trong Gradle, lifecycle task `check` là điểm tập hợp tự nhiên cho các tác vụ verification. Task `build` của Java plugin phụ thuộc vào `check` và `assemble`, vì vậy pipeline có thể gọi `check` hoặc `build` tùy mục tiêu.

## 2. Thiết kế test strategy trước khi thêm task

Test nên được chia theo phạm vi và chi phí thực thi. Tên gọi phổ biến là unit, integration, contract và end-to-end test. Không phải project nào cũng cần đủ bốn tầng, nhưng cần hiểu mỗi tầng kiểm tra điều gì.

| Loại test | Phạm vi | Phụ thuộc bên ngoài | Tốc độ tương đối |
|---|---|---|---|
| Unit test | Một class hoặc đơn vị logic nhỏ | Thường không | Nhanh |
| Integration test | Nhiều thành phần phối hợp | Có thể cần database, queue hoặc service | Trung bình |
| Contract test | Tương thích giữa provider và consumer | Có thể dùng stub/contract broker | Trung bình |
| End-to-end test | Luồng người dùng qua hệ thống | Thường cần ứng dụng và hạ tầng đầy đủ | Chậm |

### 2.1. Unit test

Unit test tập trung vào hành vi của một đơn vị code. Các dependency có thể được thay bằng fake hoặc mock khi mục tiêu là kiểm tra logic của class đang xét.

Ví dụ:

~~~java
class PriceCalculatorTest {
    private final PriceCalculator calculator = new PriceCalculator();

    @Test
    void appliesDiscountToEligibleOrder() {
        Money result = calculator.total(
            Money.of(100),
            Discount.percent(10)
        );

        assertEquals(Money.of(90), result);
    }
}
~~~

Một unit test tốt cần:

- Có tên mô tả hành vi.
- Chuẩn bị dữ liệu rõ ràng.
- Thực hiện một hành động chính.
- Kiểm tra kết quả hoặc side effect có ý nghĩa.
- Không phụ thuộc thứ tự chạy với test khác.
- Không dùng thời gian thực, random hoặc network không kiểm soát.

Đừng chỉ gọi method rồi để test pass mà không có assertion. Một test không kiểm tra điều gì có thể tạo cảm giác an toàn giả.

### 2.2. Integration test

Integration test kiểm tra cách các thành phần phối hợp, ví dụ service với repository, HTTP client với server giả lập, hoặc ứng dụng với database test.

Một integration test có thể kiểm tra:

1. Tạo dữ liệu test.
2. Gọi service hoặc endpoint thật.
3. Xác nhận dữ liệu được lưu/đọc đúng.
4. Dọn trạng thái sau test hoặc dùng database cô lập.

Nên dùng database/container riêng cho test hoặc schema tạm theo từng job. Tránh để integration test ghi vào database development hoặc production. Test phải có setup/teardown rõ ràng và có thể chạy lặp lại.

### 2.3. Contract và end-to-end test

Contract test xác nhận hai phía tuân thủ một giao ước API hoặc message. Nó hữu ích khi provider và consumer được phát triển hoặc triển khai độc lập.

End-to-end test đi qua nhiều lớp của ứng dụng, thường kiểm tra một số luồng quan trọng như đăng nhập, tạo đơn hàng hoặc thanh toán giả lập. Vì chi phí cao, nên chọn các luồng có giá trị và giữ test ổn định.

Không nên biến toàn bộ test suite thành end-to-end. Khi một test E2E fail, nhiều thành phần có thể là nguyên nhân và thời gian điều tra thường lớn hơn unit test.

## 3. Thiết lập JUnit 5 trong Gradle

Gradle Java plugin cung cấp task `test`, nhưng cần cấu hình test framework phù hợp. Với JUnit Jupiter (JUnit 5), khai báo dependency và yêu cầu Gradle dùng JUnit Platform.

Ví dụ Groovy DSL trong `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.10.2')
    testImplementation 'org.junit.jupiter:junit-jupiter'
}

tasks.test {
    useJUnitPlatform()

    testLogging {
        events 'passed', 'skipped', 'failed'
        exceptionFormat 'full'
        showStandardStreams = false
    }

    ignoreFailures = false
}
~~~

Version trong ví dụ là một mốc minh họa; hãy chọn version JUnit tương thích với Java baseline và chính sách dependency của project. Dùng BOM giúp các module JUnit Jupiter có version nhất quán.

Với Kotlin DSL, cấu hình tương đương:

~~~kotlin
plugins {
    java
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.10.2"))
    testImplementation("org.junit.jupiter:junit-jupiter")
}

tasks.test {
    useJUnitPlatform()

    testLogging {
        events("passed", "skipped", "failed")
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
    }

    ignoreFailures = false
}
~~~

### 3.1. Test source set mặc định

Java plugin dùng cấu trúc thông thường:

~~~text
src/
├── main/
│   ├── java/
│   └── resources/
└── test/
    ├── java/
    └── resources/
~~~

- `src/main/java`: source production.
- `src/main/resources`: resource production.
- `src/test/java`: unit test.
- `src/test/resources`: fixture/resource cho unit test.

Gradle compile test source và chạy test thông qua task `test`. Test runtime classpath bao gồm output production và các dependency dành cho test.

Đặt test đúng source set giúp Gradle và IDE hiểu rõ classpath, đồng thời tránh đưa test-only dependency vào artifact production.

### 3.2. Assertion phải thể hiện yêu cầu

Ví dụ kiểm tra exception:

~~~java
@Test
void rejectsNegativeQuantity() {
    assertThrows(
        IllegalArgumentException.class,
        () -> order.addItem(product, -1)
    );
}
~~~

Ví dụ kiểm tra nhiều điều kiện:

~~~java
@Test
void createsOrderWithExpectedStatusAndTotal() {
    Order order = service.create(sampleRequest);

    assertAll(
        () -> assertEquals(OrderStatus.PENDING, order.status()),
        () -> assertEquals(Money.of(120), order.total()),
        () -> assertNotNull(order.id())
    );
}
~~~

Assertion nên kiểm tra kết quả nghiệp vụ quan trọng. Tránh kiểm tra chi tiết implementation không phải contract, vì thay đổi nội bộ vô hại có thể làm test fail.

### 3.3. Tổ chức test bằng tags

JUnit 5 cho phép gắn tag để chọn nhóm test:

~~~java
@Tag("integration")
class OrderRepositoryIT {
    // integration tests
}
~~~

Có thể cấu hình test task để chạy hoặc loại trừ tag. Khi tách unit và integration tests, nên bảo đảm tag/filter không khiến một nhóm test vô tình không được chạy trong CI.

## 4. Cấu hình điều kiện thất bại của Test task

Gradle `Test` task có các thuộc tính điều khiển cách xử lý lỗi và lọc test. Những thuộc tính này cần được hiểu rõ vì cấu hình sai có thể làm pipeline pass dù một kiểm tra đáng lẽ phải fail.

### 4.1. Không bỏ qua test failures

`ignoreFailures` mặc định là false. Khi để false, test failure làm task `test` thất bại và Gradle trả exit code khác 0.

~~~groovy
tasks.withType(Test).configureEach {
    ignoreFailures = false
}
~~~

Nếu đặt `ignoreFailures = true`, Gradle ghi nhận task có lỗi nhưng không làm build thất bại vì lỗi đó. Chỉ dùng khi có một quy trình báo cáo riêng và chính sách đã cho phép. Với quality gate bắt buộc, giữ false.

Không nên bắt exception trong test rồi chỉ log lỗi. Nếu test phát hiện hành vi sai, assertion phải fail hoặc exception phải thoát ra để test engine đánh dấu test thất bại.

### 4.2. Dừng sớm khi test fail

`failFast` cho phép dừng việc thực thi các test còn lại sau khi có test failure đầu tiên:

~~~groovy
tasks.test {
    failFast = true
}
~~~

Điều này có thể rút ngắn thời gian phản hồi khi một lỗi nền tảng làm nhiều test khác thất bại. Tuy nhiên, nếu mục tiêu là thu thập nhiều lỗi độc lập trong một lần chạy, có thể để `failFast = false` để test suite tiếp tục.

Dù `failFast` bật hay tắt, task vẫn phải thất bại nếu có test fail. Nó thay đổi cách chạy test, không biến lỗi thành pass.

### 4.3. Test filter phải phát hiện selector sai

Khi chạy một test cụ thể, có thể dùng:

~~~bash
./gradlew test --tests "com.example.orders.OrderServiceTest"
~~~

Hoặc trong build script:

~~~groovy
tasks.test {
    filter {
        includeTestsMatching 'com.example.orders.*'
        failOnNoMatchingTests = true
    }
}
~~~

`failOnNoMatchingTests` giúp build thất bại khi filter đã chọn nhưng không có test nào khớp. Điều này tránh trường hợp typo tên test khiến lệnh test chạy mà không kiểm tra gì.

Tùy Gradle version và cách filter được cấu hình, hãy xác nhận thuộc tính này được hỗ trợ. Nó không thay thế chính sách kiểm tra một test suite rỗng khi không có filter.

### 4.4. Không nhầm “0 tests” với “all tests passed”

Một test task có thể không tìm thấy test nào do source set sai, engine thiếu, filter sai hoặc test bị exclude. Một task không có test được phát hiện có thể không tạo test failure thông thường.

Với suite bắt buộc, hãy bảo đảm có test được phát hiện. Có thể kiểm tra XML test report trong CI hoặc thêm bước xác minh số lượng test theo quy ước của project. `failOnNoMatchingTests` hữu ích cho trường hợp filter không khớp, nhưng không tự đặt ngưỡng số test cho mọi lần chạy không filter.

### 4.5. Timeout và test không kết thúc

Test treo có thể khiến CI chiếm worker lâu hoặc bị runner kill. Có thể dùng timeout ở cấp task:

~~~groovy
tasks.withType(Test).configureEach {
    timeout = java.time.Duration.ofMinutes(15)
}
~~~

Timeout nên dựa trên đặc tính test suite và môi trường CI. Một timeout quá ngắn tạo false failure; timeout quá dài làm chậm feedback. Với test cần chờ service bên ngoài, ưu tiên timeout cụ thể ở HTTP/database client và polling có giới hạn thay vì chờ vô hạn.

## 5. Tách integration test khỏi unit test

Khi project cần integration test, có thể tạo source set và task riêng. Nhờ vậy, developer có thể chạy unit tests nhanh trong lúc phát triển, còn CI chạy cả hai tầng theo policy.

Ví dụ Groovy DSL:

~~~groovy
sourceSets {
    integrationTest {
        compileClasspath += sourceSets.main.output + configurations.testRuntimeClasspath
        runtimeClasspath += output + compileClasspath
    }
}

configurations {
    integrationTestImplementation.extendsFrom testImplementation
    integrationTestRuntimeOnly.extendsFrom testRuntimeOnly
}

tasks.register('integrationTest', Test) {
    description = 'Runs integration tests.'
    group = 'verification'

    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath

    useJUnitPlatform()
    shouldRunAfter tasks.test
    ignoreFailures = false
}

tasks.named('check') {
    dependsOn tasks.named('integrationTest')
}
~~~

Đây là một cách tổ chức source set phổ biến. Với project mới hoặc Gradle version hỗ trợ, có thể cân nhắc JVM Test Suites DSL để mô tả test suite theo model hiện đại hơn. Hãy chọn một cách nhất quán và kiểm tra dependency configuration của source set.

Cấu trúc thư mục tương ứng:

~~~text
src/
├── main/
├── test/
└── integrationTest/
    ├── java/
    └── resources/
~~~

### 5.1. Đảm bảo integration test có dependency riêng

Integration test có thể cần database driver, Testcontainers, HTTP mock server hoặc fixture. Đặt dependency trong `integrationTestImplementation`/`integrationTestRuntimeOnly` thay vì đưa tất cả vào production dependencies.

Nếu integration test dùng chung thư viện test với unit test, có thể kế thừa configuration như ví dụ. Với test engine, cần bảo đảm runtime configuration chứa engine tương ứng.

### 5.2. Gắn integration test vào lifecycle `check`

Task custom sẽ không tự chạy chỉ vì được khai báo. Nếu quality gate yêu cầu integration test luôn chạy khi gọi `check`, cần nối task vào `check` bằng `dependsOn`.

`shouldRunAfter` chỉ sắp xếp thứ tự khi cả hai task đã nằm trong task graph. Nó không tự đưa task vào graph. `dependsOn` mới là quan hệ đảm bảo integration test được gọi cùng `check`.

Đây là khác biệt quan trọng: tạo task thành công không có nghĩa pipeline đã thực thi task đó.

### 5.3. Điều kiện môi trường cho integration test

Nếu integration test cần service, CI phải cung cấp service trước khi chạy task. Có thể dùng container, service container của CI hoặc test fixture cô lập.

Nếu môi trường không được chuẩn bị, test cần fail với thông báo rõ như “database test endpoint is unavailable”, thay vì skip im lặng. Nếu có lý do hợp lệ để không chạy integration test ở một job cụ thể, policy cần ghi rõ job nào được miễn và job nào bắt buộc chạy.

## 6. Dùng lifecycle task làm quality gate

Java plugin tạo các lifecycle task chính:

- `assemble`: tạo artifact.
- `check`: chạy các verification tasks.
- `build`: kết hợp `assemble` và `check`.

Vì vậy, CI thường gọi:

~~~bash
./gradlew clean check
~~~

hoặc:

~~~bash
./gradlew clean build
~~~

`check` phù hợp khi pipeline chỉ cần xác minh chất lượng. `build` phù hợp khi cần cả verification và artifact. Nếu pipeline có integration test hoặc coverage verification riêng, phải nối chúng vào `check` hoặc gọi trực tiếp trong command.

### 6.1. Kiểm tra task đã được nối vào graph chưa

Có thể xem task graph hoặc log:

~~~bash
./gradlew check --dry-run
~~~

`--dry-run` hiển thị task sẽ được thực thi mà không chạy action. Dùng nó để xác nhận task custom như `integrationTest` hoặc `jacocoTestCoverageVerification` đã được đưa vào lifecycle.

Nếu task không xuất hiện, kiểm tra `dependsOn`, plugin và điều kiện task. Không chỉ nhìn vào file build script rồi giả định task đã được chạy.

### 6.2. Task phụ thuộc và task ordering

Ba khái niệm dễ nhầm:

| Cấu hình | Tác dụng |
|---|---|
| `dependsOn` | Đưa task dependency vào task graph và chạy trước task phụ thuộc |
| `mustRunAfter` | Yêu cầu thứ tự nếu cả hai task đã có trong graph |
| `shouldRunAfter` | Đề xuất thứ tự nếu cả hai task đã có trong graph; có thể bỏ qua để giải quyết constraint |

Quality gate bắt buộc cần quan hệ dependency phù hợp. Chỉ dùng ordering rule sẽ không bảo đảm gate được chạy.

### 6.3. Một task bị skip không nhất thiết là pass

Task có thể bị skip do `onlyIf`, `enabled = false`, không có source hoặc điều kiện môi trường. Một số trường hợp skip là hợp lệ; một số trường hợp cho thấy pipeline thiếu kiểm tra.

Nếu một gate là bắt buộc, hãy xem lý do task bị skip và xác định điều kiện miễn chạy có được policy cho phép hay không. Không dùng `onlyIf` để né một lỗi test hoặc lint.

## 7. Đặt ngưỡng coverage bằng JaCoCo

Coverage cho biết phần code được thực thi khi chạy test. JaCoCo có thể tạo report và kiểm tra ngưỡng coverage.

Áp dụng plugin:

~~~groovy
plugins {
    id 'java'
    id 'jacoco'
}

jacoco {
    toolVersion = '0.8.12'
}
~~~

Version JaCoCo trong ví dụ là minh họa. Chọn version hỗ trợ class-file version của JDK dùng để compile và runtime Gradle của project.

Cấu hình report:

~~~groovy
tasks.test {
    finalizedBy tasks.jacocoTestReport
}

tasks.jacocoTestReport {
    dependsOn tasks.test

    reports {
        xml.required = true
        html.required = true
    }
}
~~~

HTML report giúp developer xem class/method/line chưa được cover. XML report phù hợp với CI hoặc công cụ phân tích bên ngoài.

### 7.1. Định nghĩa ngưỡng thất bại

Task `jacocoTestCoverageVerification` có thể fail nếu coverage thấp hơn giới hạn:

~~~groovy
tasks.jacocoTestCoverageVerification {
    violationRules {
        rule {
            limit {
                counter = 'LINE'
                value = 'COVEREDRATIO'
                minimum = 0.80
            }
        }
    }
}
~~~

Trong ví dụ, line coverage phải đạt tối thiểu 80%. Nếu tỷ lệ thấp hơn, task thất bại và build có exit code khác 0 khi task nằm trong graph.

Ngưỡng cần được chọn theo baseline thực tế và rủi ro của project. Đặt ngưỡng rất cao cho code cũ có thể tạo áp lực viết test hời hợt; đặt quá thấp có thể không bảo vệ được các phần quan trọng.

### 7.2. Nối coverage verification vào `check`

JaCoCo plugin tạo task verification nhưng không nên giả định nó tự tham gia lifecycle `check`. Hãy nối rõ:

~~~groovy
tasks.named('check') {
    dependsOn tasks.named('jacocoTestCoverageVerification')
}

tasks.named('jacocoTestCoverageVerification') {
    dependsOn tasks.named('test')
}
~~~

Nhờ vậy, gọi `check` sẽ chạy test, tính coverage và kiểm tra ngưỡng. Nếu không có dependency này, pipeline có thể chạy `check` mà không thực hiện coverage gate.

### 7.3. Chọn counter phù hợp

JaCoCo hỗ trợ các counter như:

- INSTRUCTION: bytecode instructions.
- LINE: source lines.
- BRANCH: nhánh điều kiện.
- COMPLEXITY: độ phức tạp.
- METHOD: methods.
- CLASS: classes.

Ví dụ yêu cầu branch coverage:

~~~groovy
tasks.jacocoTestCoverageVerification {
    violationRules {
        rule {
            limit {
                counter = 'BRANCH'
                value = 'COVEREDRATIO'
                minimum = 0.70
            }
        }
    }
}
~~~

Line coverage 80% không có nghĩa 80% nhánh logic đã được kiểm tra. Với code nhiều điều kiện, branch coverage có thể cung cấp tín hiệu khác.

### 7.4. Exclude code khỏi coverage có chủ đích

Một số class sinh tự động, DTO đơn giản hoặc cấu hình không thuộc phạm vi coverage có thể được loại khỏi report. Việc exclude cần được thống nhất và áp dụng nhất quán giữa report và verification.

Không nên loại bỏ class khó test chỉ để làm tỷ lệ đẹp hơn. Hãy phân biệt code không cần kiểm thử trực tiếp với code quan trọng đang thiếu test.

### 7.5. Coverage không thay thế assertion và review

Coverage chỉ ghi nhận code đã được thực thi. Một test có thể đi qua dòng code mà không xác nhận kết quả đúng. Vì vậy:

- Đọc assertion và dữ liệu test.
- Bổ sung case biên và case lỗi.
- Ưu tiên branch có rủi ro.
- Kết hợp test với review, static analysis và kiểm tra thiết kế.

Coverage là một gate định lượng, không phải chứng nhận chất lượng hoàn chỉnh.

## 8. Static analysis và quy tắc source code

Static analysis kiểm tra source mà không cần chạy toàn bộ ứng dụng. Nó có thể phát hiện style violation, lỗi tiềm ẩn, code phức tạp, API nguy hiểm hoặc pattern không được phép.

Gradle có các plugin như Checkstyle và PMD. Có thể thêm SpotBugs hoặc công cụ chuyên biệt theo nhu cầu.

### 8.1. Checkstyle

Checkstyle kiểm tra quy tắc format và style Java. Ví dụ:

~~~groovy
plugins {
    id 'java'
    id 'checkstyle'
}

checkstyle {
    toolVersion = '10.12.4'
    configFile = file('config/checkstyle/checkstyle.xml')
}

tasks.withType(Checkstyle).configureEach {
    ignoreFailures = false
}
~~~

Gradle Checkstyle plugin tạo task cho các source set và tích hợp các task verification vào lifecycle `check`. Nếu có custom source set, kiểm tra task tương ứng đã được cấu hình và chạy hay chưa.

`ignoreFailures = false` bảo đảm violation được xem là task failure. Cấu hình ruleset phải được commit cùng project để local và CI dùng cùng quy tắc.

### 8.2. PMD

PMD kiểm tra các pattern có thể chỉ ra lỗi hoặc code khó bảo trì:

~~~groovy
plugins {
    id 'pmd'
}

pmd {
    toolVersion = '6.55.0'
    consoleOutput = true
}

tasks.withType(Pmd).configureEach {
    ignoreFailures = false
}
~~~

Version minh họa cần được chọn theo JDK, Gradle và ruleset của project. Với một số phiên bản PMD, hỗ trợ Java language level mới có thể khác nhau. Kiểm tra compatibility trước khi nâng compiler target.

### 8.3. Formatting là gate riêng

Formatting tool như Spotless có thể kiểm tra code có đúng format hay không. Thường có hai thao tác:

- Check: xác định file có vi phạm format; nếu có thì fail.
- Apply: tự động sửa format.

CI nên chạy check. Developer có thể chạy apply trước khi commit. Không nên để CI tự sửa file trong checkout rồi trả pass mà không đưa thay đổi đó về pull request.

### 8.4. Static analysis cần policy rõ ràng

Một ruleset có thể tạo quá nhiều warning và làm developer bỏ qua report. Nên phân loại:

- Error nghiêm trọng: fail ngay.
- Warning có rủi ro: fail theo ngưỡng hoặc policy.
- Style preference: có thể dùng auto-format.
- Finding cũ: quản lý baseline và giảm dần theo kế hoạch.

Nếu cho phép warning cũ, nên đặt điều kiện không tạo thêm violation mới hoặc có issue theo dõi. Đừng đặt `ignoreFailures = true` cho mọi task rồi gọi pipeline đó là quality gate.

## 9. Tổ chức nhiều quality gates trong một build

Một project có thể có nhiều task verification. Mục tiêu là để một lệnh chuẩn chạy được toàn bộ gate bắt buộc.

Ví dụ:

~~~groovy
tasks.named('check') {
    dependsOn tasks.named('integrationTest')
    dependsOn tasks.named('jacocoTestCoverageVerification')
}
~~~

Nếu Checkstyle plugin đã gắn task của nó vào `check`, không cần thêm dependency trùng lặp. Nếu có task custom hoặc plugin bên ngoài không tự nối vào lifecycle, thêm dependency rõ ràng.

Có thể xem graph trước khi chạy:

~~~bash
./gradlew check --dry-run
~~~

Một lệnh CI thường dùng:

~~~bash
./gradlew clean check --stacktrace
~~~

Nếu cần artifact:

~~~bash
./gradlew clean build --stacktrace
~~~

### 9.1. Chia gate theo pipeline stage

Không nhất thiết mọi kiểm tra đều chạy ở mọi bước. Một cách tổ chức thường gặp:

| Stage | Gate | Mục tiêu |
|---|---|---|
| Pull request | Compile, unit tests, formatting, static analysis | Feedback nhanh |
| Main branch | Integration tests, coverage, dependency checks | Kiểm tra sâu hơn |
| Release | Full test suite, artifact verification, security/license policy | Đủ điều kiện phát hành |

Điều kiện miễn chạy phải rõ ràng. Nếu integration test chỉ chạy trên main branch, pull request vẫn cần có test phù hợp để không merge code chưa được kiểm tra. Quy tắc này phải được thể hiện trong pipeline configuration.

### 9.2. Không để task bắt buộc chỉ chạy thủ công

Nếu tài liệu nói phải chạy integration test nhưng CI chỉ gọi `assemble`, gate đó không bảo vệ được branch. Hãy gắn task vào `check` hoặc gọi trực tiếp trong pipeline.

Tương tự, nếu coverage verification là bắt buộc, phải nối task verification vào task lifecycle được CI gọi. Việc report coverage tồn tại không chứng minh ngưỡng đã được kiểm tra.

## 10. Failure semantics: điều kiện nào làm build thất bại?

Một quality gate nên có điều kiện pass/fail cụ thể và dễ diễn giải.

| Gate | Điều kiện pass | Điều kiện fail |
|---|---|---|
| Compile | Source compile thành công | Compiler error |
| Unit test | Tất cả test được chạy đều pass | Assertion/error/exception hoặc timeout |
| Integration test | Tương tác với service test đúng yêu cầu | Service không sẵn sàng, assertion fail hoặc timeout |
| Test filter | Có test khớp selector | Không có test khớp khi policy yêu cầu |
| Coverage | Coverage đạt ngưỡng | Tỷ lệ thấp hơn ngưỡng |
| Checkstyle/PMD | Không vượt policy | Violation theo ruleset |
| Formatting | File đã đúng format | `spotlessCheck` hoặc formatter check fail |
| Dependency policy | Dependency đạt policy | Version/license/vulnerability vi phạm ngưỡng |
| Artifact verification | Artifact hợp lệ | Metadata, signature hoặc cấu trúc không đạt |

Điều kiện phải được ghi trong build script hoặc pipeline, không chỉ nằm trong tài liệu hướng dẫn.

### 10.1. Tránh cấu hình bỏ qua lỗi

Các cấu hình sau có thể làm giảm độ nghiêm ngặt của gate:

- `ignoreFailures = true`.
- `enabled = false`.
- `onlyIf` luôn trả false do biến môi trường thiếu.
- Exclude toàn bộ package/test quan trọng.
- Test filter không khớp mà không fail.
- Task verification không được nối vào lifecycle.
- Script CI dùng `|| true` sau lệnh build.
- Shell script không bật chế độ xử lý lỗi và vô tình trả exit code của lệnh cuối khác.

Hãy xem xét mọi điều kiện skip như một policy: task có được phép bỏ qua trong job này không, và pipeline có kiểm tra điều đó không?

### 10.2. Không nuốt exit code trong CI

Gradle trả exit code khác 0 khi build thất bại. CI runner dựa vào exit code đó để đánh dấu job fail.

Ví dụ shell:

~~~bash
set -e
./gradlew clean check --stacktrace
~~~

Nếu gọi Gradle trong script rồi ghi log, hãy bảo đảm script vẫn trả về exit code của Gradle. Không dùng `|| true` để làm pipeline xanh sau một lỗi quality gate.

Trong PowerShell, kiểm tra `$LASTEXITCODE` sau khi gọi chương trình native nếu script tiếp tục chạy các lệnh khác. Không dựa vào `$?` sau một lệnh PowerShell khác để kết luận exit code Gradle.

### 10.3. `--continue` để thu thập nhiều lỗi

Có thể dùng:

~~~bash
./gradlew check --continue
~~~

`--continue` yêu cầu Gradle tiếp tục các task độc lập có thể chạy sau khi một task thất bại. Build cuối cùng vẫn thất bại nếu có task failure. Task phụ thuộc vào task đã fail không thể chạy như thể prerequisite đã thành công.

Tùy chọn này hữu ích khi muốn thu thập nhiều report trong một lượt CI. Nó không phải cách bỏ qua quality gate.

### 10.4. Phân biệt FAILED, SKIPPED và UP-TO-DATE

Trong output Gradle:

- `FAILED`: task thất bại.
- `SKIPPED`: task không thực thi do điều kiện hoặc không có việc cần làm theo trạng thái skip.
- `UP-TO-DATE`: task output hiện tại phù hợp execution history nên không cần chạy lại.
- `FROM-CACHE`: output được khôi phục từ build cache.
- `NO-SOURCE`: task không có source input phù hợp.

Một gate `UP-TO-DATE` vẫn có thể hợp lệ nếu Gradle đã xác định inputs/outputs không đổi. Một gate `SKIPPED` cần được hiểu theo policy. Đừng xem mọi task không có chữ FAILED là đã thực hiện kiểm tra đầy đủ.

## 11. Test report và cách điều tra khi gate fail

Khi test task thất bại, cần report có tên test, exception, stack trace và kết quả assertion.

Gradle Java plugin thường tạo report:

~~~text
build/
├── reports/
│   └── tests/
│       └── test/
│           └── index.html
└── test-results/
    └── test/
        └── TEST-*.xml
~~~

HTML report phù hợp để developer đọc. XML report phù hợp để CI đọc và tích hợp với hệ thống test reporting.

Với integration test, report nằm trong thư mục tương ứng với tên task, ví dụ `build/reports/tests/integrationTest`.

### 11.1. Đọc failure theo nguyên nhân gốc

Khi test fail:

1. Xác định test class và test method.
2. Đọc assertion message.
3. Xem expected và actual.
4. Đọc stack trace tới dòng code đầu tiên thuộc project.
5. Kiểm tra fixture và external service.
6. Chạy riêng test để tái hiện.
7. Chạy lại suite sau khi sửa để phát hiện regression.

Không nên chỉ nhìn summary “1 test failed”. Chi tiết report thường cho biết dữ liệu đầu vào, exception và vị trí lỗi.

### 11.2. Chạy riêng test để điều tra

Ví dụ:

~~~bash
./gradlew test --tests "com.example.orders.OrderServiceTest"
~~~

Có thể chạy một method theo selector được Gradle/JUnit hỗ trợ:

~~~bash
./gradlew test --tests "com.example.orders.OrderServiceTest.rejectsInvalidOrder"
~~~

Khi điều tra, hãy giữ nguyên Java/toolchain và environment gần với CI. Nếu chỉ chạy bằng IDE runner, có thể vẫn chưa tái hiện được khác biệt đang cần tìm.

### 11.3. Lưu report ngay cả khi job fail

CI nên cấu hình upload test reports như artifacts trong bước chạy sau build, với điều kiện luôn thực thi kể cả khi build step fail. Tên cú pháp phụ thuộc nền tảng CI.

Lưu HTML/XML report giúp reviewer xem failure sau khi job kết thúc. Nếu chỉ lưu report khi build pass, thông tin hữu ích nhất lại biến mất đúng lúc cần điều tra.

## 12. Làm cho test ổn định và có giá trị

Một quality gate tốt cần phản ánh lỗi sản phẩm, không tạo false failure do test phụ thuộc thời gian, thứ tự hoặc môi trường.

### 12.1. Không phụ thuộc thứ tự test

Mỗi test nên tự chuẩn bị dữ liệu và dọn trạng thái của mình. Không để test A tạo record mà test B cần, vì CI có thể chạy test song song hoặc thứ tự khác IDE.

### 12.2. Kiểm soát thời gian và random

Dùng Clock có thể inject thay vì gọi trực tiếp thời gian hệ thống trong logic cần kiểm thử. Seed random rõ ràng nếu kết quả test phụ thuộc random. Với test dựa trên thời gian, dùng fixed clock hoặc time window có giới hạn.

### 12.3. Không dùng service production

Integration test phải dùng môi trường test riêng. Dữ liệu cần được cô lập theo job/test run, tránh xóa hoặc sửa dữ liệu thật.

### 12.4. Quản lý flaky tests

Flaky test có lúc pass, lúc fail với cùng code và input. Nguyên nhân thường là race, sleep tùy tiện, external service không ổn định, shared state hoặc resource contention.

Không nên chỉ thêm retry vô hạn hoặc đánh dấu test ignore. Hãy ghi nhận tần suất, xác định điều kiện tái hiện, sửa nguyên nhân và chỉ dùng retry có giới hạn như biện pháp tạm thời được theo dõi.

### 12.5. Chạy song song có kiểm soát

Gradle có thể fork nhiều test worker. Nếu test chia sẻ database/schema/file hoặc port cố định, chạy song song có thể tạo xung đột.

Có thể giới hạn worker trong task:

~~~groovy
tasks.withType(Test).configureEach {
    maxParallelForks = 2
}
~~~

Giá trị phù hợp phụ thuộc CPU, memory và cách test cô lập state. Giảm parallelism có thể giúp chẩn đoán nhưng không thay thế việc sửa test phụ thuộc shared state.

## 13. Ví dụ build.gradle tổng hợp

Ví dụ dưới đây tập hợp unit tests, integration tests, JaCoCo và Checkstyle vào quality gate `check`. Đây là cấu hình minh họa cho Groovy DSL; cần điều chỉnh version plugin, test dependencies và source set theo project.

~~~groovy
plugins {
    id 'java'
    id 'jacoco'
    id 'checkstyle'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.10.2')
    testImplementation 'org.junit.jupiter:junit-jupiter'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
    ignoreFailures = false

    testLogging {
        events 'failed', 'skipped'
        exceptionFormat 'full'
    }
}

tasks.test {
    failFast = false
    finalizedBy tasks.jacocoTestReport
}

sourceSets {
    integrationTest {
        compileClasspath += sourceSets.main.output + configurations.testRuntimeClasspath
        runtimeClasspath += output + compileClasspath
    }
}

configurations {
    integrationTestImplementation.extendsFrom testImplementation
    integrationTestRuntimeOnly.extendsFrom testRuntimeOnly
}

tasks.register('integrationTest', Test) {
    group = 'verification'
    description = 'Runs integration tests.'
    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath
    shouldRunAfter tasks.test
    ignoreFailures = false
}

jacoco {
    toolVersion = '0.8.12'
}

tasks.jacocoTestReport {
    dependsOn tasks.test
    reports {
        xml.required = true
        html.required = true
    }
}

tasks.jacocoTestCoverageVerification {
    dependsOn tasks.test
    violationRules {
        rule {
            limit {
                counter = 'LINE'
                value = 'COVEREDRATIO'
                minimum = 0.80
            }
        }
    }
}

checkstyle {
    toolVersion = '10.12.4'
    configFile = file('config/checkstyle/checkstyle.xml')
}

tasks.withType(Checkstyle).configureEach {
    ignoreFailures = false
}

tasks.named('check') {
    dependsOn tasks.named('integrationTest')
    dependsOn tasks.named('jacocoTestCoverageVerification')
}
~~~

Trong ví dụ này:

- `test` chạy JUnit Platform và không bỏ qua test failures.
- `integrationTest` có source set và classpath riêng.
- `jacocoTestReport` tạo HTML/XML report.
- `jacocoTestCoverageVerification` fail nếu line coverage thấp hơn 80%.
- Checkstyle task không bỏ qua violations.
- `check` gọi integration tests và coverage verification cùng các verification tasks mà plugin đã nối vào lifecycle.

Khi áp dụng vào project thực tế, kiểm tra task graph bằng `./gradlew check --dry-run`. Nếu task custom có điều kiện môi trường, hãy xác nhận job CI đã cung cấp điều kiện đó và task không bị skip ngoài ý muốn.

## 14. Cổng chất lượng trong CI

CI nên thực thi cùng một lệnh chuẩn mà developer có thể chạy local. Với Gradle Java project, một lựa chọn là:

~~~bash
./gradlew clean check --stacktrace
~~~

Nếu cần artifact:

~~~bash
./gradlew clean build --stacktrace
~~~

CI phải fail khi lệnh trả exit code khác 0. Cần tránh pipeline step tiếp tục và ghi đè trạng thái thất bại bằng một lệnh cuối cùng thành công.

### 14.1. Phân biệt required checks và advisory checks

Không phải mọi công cụ đều cần chặn merge ngay từ đầu. Có thể phân chia:

- Required gate: compile, unit tests, security rule nghiêm trọng, coverage threshold đã thống nhất.
- Advisory: metric hoặc report đang được theo dõi để xây dựng baseline.
- Migration gate: cho phép legacy violations nhưng không cho tăng thêm vi phạm mới.

Nếu một check chỉ mang tính advisory, hiển thị rõ trạng thái và không gọi nó là required quality gate. Khi nâng từ advisory thành required, thông báo policy và xử lý baseline trước.

### 14.2. Bảo vệ nhánh bằng required status checks

Cấu hình CI pass không tự ngăn merge nếu repository không yêu cầu status check đó. Branch protection/ruleset cần đánh dấu job quality gate là required theo chính sách nhóm.

Đảm bảo job chạy trên đúng commit của pull request, không chỉ chạy trên nhánh mặc định. Nếu có nhiều workflow, chọn check đại diện cho toàn bộ gate bắt buộc.

### 14.3. Tách report khỏi quyết định pass/fail

Report giúp hiểu kết quả; gate quyết định pass/fail. Một report có thể được tạo thành công dù coverage dưới ngưỡng, nhưng task verification vẫn phải fail.

Ngược lại, report không được tạo do test task fail không có nghĩa CI nên bỏ qua test failure. Cần upload report nào đã tồn tại và giữ nguyên exit code của build.

## 15. Tránh những quality gate gây hiểu nhầm

### 15.1. Không đặt coverage threshold tùy tiện

Nếu baseline hiện tại là 45%, đặt ngay 90% có thể làm cả nhóm tập trung viết test để tăng số thay vì kiểm tra hành vi rủi ro. Có thể bắt đầu bằng baseline, sau đó nâng ngưỡng có kế hoạch.

Với code mới, có thể áp dụng ngưỡng cao hơn hoặc yêu cầu test cho module quan trọng. Nếu công cụ hỗ trợ diff coverage, đó có thể là cách tập trung vào phần thay đổi; vẫn cần test toàn suite cho regression.

### 15.2. Không loại bỏ test chỉ vì đang fail

Một test fail có thể chỉ ra regression thật. Nếu test không còn đúng do requirement thay đổi, cập nhật test cùng với implementation và ghi rõ lý do. Không xóa test hoặc gắn ignore chỉ để pipeline pass.

### 15.3. Không dùng `onlyIf` để giấu thiếu service

Nếu integration test yêu cầu database nhưng CI không cung cấp, task bị skip có thể làm pipeline xanh giả. Hãy chuẩn bị service hoặc để task fail rõ ràng khi điều kiện bắt buộc không có.

Nếu có job lint-only không cần integration tests, hãy dùng task riêng và tên job phản ánh phạm vi; đừng gọi nó là full verification.

### 15.4. Không để warning không có giới hạn

Nếu static analysis tạo hàng nghìn warning, developer khó phân biệt lỗi mới. Có thể baseline các warning cũ, nhưng cần chính sách không tăng thêm hoặc một kế hoạch giảm nợ kỹ thuật. Quality gate cần có ngưỡng và owner.

### 15.5. Không để pipeline thành công khi task không được gọi

Một task được định nghĩa nhưng không có trong graph không kiểm tra gì. Dùng `check --dry-run`, đọc CI command và xem log để xác nhận các gate bắt buộc đã thực thi.

## 16. Checklist thiết kế quality gate

Trước khi đưa gate vào CI, hãy xác định:

- [ ] Mỗi test suite đang kiểm tra phạm vi nào?
- [ ] Unit tests có chạy qua Gradle task `test` không?
- [ ] Integration tests có task/source set riêng khi cần không?
- [ ] Integration test service có được provision trong CI không?
- [ ] Test failures có làm task thất bại không?
- [ ] Có test filter nào cần `failOnNoMatchingTests` không?
- [ ] Có policy phát hiện test suite rỗng không?
- [ ] Timeout và parallelism có phù hợp không?
- [ ] Coverage report có được tạo và lưu lại không?
- [ ] Coverage verification có ngưỡng cụ thể không?
- [ ] Coverage verification đã được nối vào `check` chưa?
- [ ] Static analysis có ruleset/version được quản lý không?
- [ ] `ignoreFailures` có đang bật ở task bắt buộc không?
- [ ] Task custom đã được nối vào lifecycle chưa?
- [ ] Task bắt buộc có bị skip bởi `onlyIf` hoặc `enabled` không?
- [ ] CI có giữ exit code thất bại của Gradle không?
- [ ] Test report được upload ngay cả khi job fail không?
- [ ] Branch protection yêu cầu đúng CI status check không?
- [ ] Developer có một lệnh local tương đương CI không?
- [ ] Gate có ổn định, tái lập và có thông báo đủ rõ để xử lý không?

## Kết luận

Thêm kiểm thử và cổng chất lượng trong Gradle cần nhiều hơn việc tạo một task test. Hãy thiết kế test strategy theo phạm vi, cấu hình framework và assertion rõ ràng, tách integration tests khi cần, rồi tập hợp mọi verification task bắt buộc qua lifecycle `check`.

Đặt điều kiện thất bại cụ thể: test failure phải làm task fail, coverage dưới ngưỡng phải làm verification fail, static analysis phải tuân theo policy, và CI phải giữ nguyên exit code của Gradle. Kiểm tra task graph để chắc chắn gate thực sự chạy, lưu test reports kể cả khi pipeline thất bại, và yêu cầu status check tương ứng trước khi merge. Khi tiêu chí pass/fail được mã hóa rõ ràng và có thể tái hiện local, quality gate trở thành một phần đáng tin cậy của quy trình phát triển.

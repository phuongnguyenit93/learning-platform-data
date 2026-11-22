# Lưu báo cáo, log và bằng chứng khi CI thất bại

Khi một test thất bại trên máy developer, người viết test có thể xem console, debugger và trạng thái môi trường ngay lập tức. Trên CI, job thường kết thúc sau khi ghi một dòng `BUILD FAILED`; nếu báo cáo, log và dữ liệu chẩn đoán không được lưu thành artifact, việc tái hiện lỗi sẽ khó hơn nhiều. Vì vậy, một pipeline kiểm thử Spring cần chuẩn bị đầu ra có thể đọc lại sau khi job kết thúc, kể cả khi lệnh test trả exit code khác 0.

Việc lưu bằng chứng nên bao phủ cả kết quả của test framework, log của ứng dụng, thông tin môi trường và các dữ liệu bổ sung phù hợp với loại test. Các artifact phải được gắn với đúng lần chạy, được tải lên ngay cả khi test thất bại và được bảo vệ khỏi việc vô tình công khai thông tin nhạy cảm.

## 1. Những bằng chứng cần giữ lại

Một dòng stack trace thường chưa đủ để giải thích một lỗi trên CI. Hãy xác định loại bằng chứng nào giúp trả lời câu hỏi: test nào thất bại, assertion nào không đúng, Spring context được tạo ra sao, request nào được gửi, và môi trường lúc đó khác gì so với lần chạy thành công.

| Loại bằng chứng | Nội dung | Nguồn thường gặp |
|---|---|---|
| Test report | Tên test, trạng thái pass/fail/skip, thời gian, exception và stack trace | JUnit XML, Surefire/Failsafe, Gradle test report |
| HTML report | Kết quả tổng hợp và chi tiết từng test để đọc trong trình duyệt | Gradle HTML report hoặc report plugin |
| Test output | `System.out`, `System.err`, log do test ghi ra | Gradle test logging, Maven Surefire output files |
| Application log | Log của Spring Boot, controller, service, repository và HTTP client | Logback/Log4j2, file log của test |
| Context diagnostics | Quá trình load/cache/close `ApplicationContext`, condition evaluation | Spring TestContext logs, Spring Boot diagnostics |
| Request/response evidence | Method, URL, headers đã lọc, status và body đã che dữ liệu nhạy cảm | Mock server, WebTestClient, MockMvc, client logging |
| UI evidence | Screenshot, video, browser console và network trace | Browser test framework |
| Runtime diagnostics | Thread dump, JVM crash log, heap dump khi cần | `jstack`, `jcmd`, JVM flags |
| External service logs | Container, database, message broker hoặc service giả lập | Docker/Testcontainers và CI service logs |
| Run metadata | Commit, branch, JDK, OS, build tool, test filter, retry và matrix dimension | CI variables và build metadata |

Không phải test nào cũng cần mọi loại artifact. Unit test thường chỉ cần report và log; test tích hợp có thể cần thêm container/service logs; test UI có thể cần screenshot hoặc video; test treo có thể cần thread dump.

## 2. Phân biệt test report với log

Test report trả lời câu hỏi *test nào đã chạy và kết quả là gì*. Log cung cấp ngữ cảnh về *điều gì đã xảy ra trong lúc test chạy*.

JUnit XML thường chứa testcase, thời lượng, failure/error và stack trace. CI có thể đọc XML để hiển thị test thất bại ngay trong giao diện pull request. HTML report giúp developer xem kết quả chi tiết mà không phải đọc XML thô.

Log có thể cho biết request được gửi tới endpoint nào, Spring chọn profile nào, context cache có được tái sử dụng không hoặc service trả lỗi từ đâu. Log không thay thế test report: log có thể không ghi được nếu JVM bị kill, trong khi XML có thể được ghi sau từng test hoặc sau mỗi fork tùy runner.

Với Maven, Surefire thường lưu kết quả unit test trong `target/surefire-reports/`; Failsafe lưu kết quả integration test trong `target/failsafe-reports/`. Với Gradle, kết quả thường nằm trong `build/test-results/test/` và HTML report trong `build/reports/tests/test/`. Đường dẫn có thể thay đổi nếu dự án cấu hình task hoặc report destination riêng.

## 3. Giữ lại JUnit XML và HTML report

### Maven Surefire và Failsafe

Surefire chạy unit test; Failsafe thường chạy integration test qua các phase `integration-test` và `verify`. Khi test thất bại, Maven vẫn có thể tạo report trước khi trả exit code khác 0. CI cần upload các thư mục report sau lệnh build.

Có thể cấu hình Surefire để lưu stdout/stderr của từng test vào file:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <redirectTestOutputToFile>true</redirectTestOutputToFile>
    </configuration>
</plugin>
```

Đặt cấu hình tương tự cho `maven-failsafe-plugin` nếu muốn lưu output của integration test. Report XML và file output theo test giúp xem lại lỗi mà không cần toàn bộ console log của Maven.

Các đường dẫn mặc định thường cần upload:

```text
target/surefire-reports/
target/failsafe-reports/
```

Nếu dự án có nhiều module Maven, dùng glob như `**/target/surefire-reports/**` và `**/target/failsafe-reports/**` để thu thập report từ từng module.

### Gradle Test

Gradle tạo JUnit XML và HTML report cho task `Test`. Có thể yêu cầu test logging hiển thị đầy đủ exception và standard streams trong console:

```groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()

    testLogging {
        events "failed", "skipped"
        exceptionFormat "full"
        showStandardStreams = true
    }
}
```

`showStandardStreams` hữu ích khi test ghi thông tin ra `System.out` hoặc `System.err`, nhưng không nên dùng `println` làm cơ chế logging chính cho ứng dụng. Log framework cho phép phân cấp mức độ, định dạng và định tuyến output rõ ràng hơn.

Các thư mục mặc định thường cần upload:

```text
build/test-results/test/
build/reports/tests/test/
```

Với integration test chạy bằng task riêng, ví dụ `integrationTest`, cần thu thập cả `build/test-results/integrationTest/` và `build/reports/tests/integrationTest/`. Hãy xem tên task thực tế trong dự án thay vì giả định mọi test đều nằm trong task `test`.

## 4. Cấu hình log hữu ích cho Spring Test

Khi Spring context thất bại lúc khởi tạo, log mặc định đôi khi chỉ cho thấy một exception ở cuối chuỗi. Bật log có mục tiêu để biết Spring đang tạo, tái sử dụng hoặc đóng context nào.

Ví dụ trong `src/test/resources/application-test.properties`:

```properties
logging.level.org.springframework.test.context=DEBUG
logging.level.org.springframework.test.context.cache=DEBUG
logging.level.org.springframework.boot.test.context=DEBUG
```

Hoặc YAML:

```yaml
logging:
  level:
    org.springframework.test.context: DEBUG
    org.springframework.test.context.cache: DEBUG
    org.springframework.boot.test.context: DEBUG
```

Các logger này hữu ích khi điều tra context cache, bootstrap và lỗi load context. Chỉ bật mức DEBUG trong test profile hoặc job chẩn đoán khi cần, vì log có thể rất nhiều và có thể làm tăng thời gian CI.

Nếu dự án không dùng Spring Boot, cấu hình logger trong `src/test/resources/logback-test.xml` hoặc file cấu hình tương ứng của logging framework. Đảm bảo cấu hình test được nạp trong test runtime; file cấu hình chỉ có ở main resources có thể không phù hợp với mục đích chẩn đoán riêng cho test.

Với Spring Boot, `debug=true` có thể in condition evaluation report trong một số ngữ cảnh khởi động. Nó hữu ích khi cần biết auto-configuration nào được áp dụng, nhưng không thay thế log test context hoặc stack trace đầy đủ.

## 5. Làm cho log có thể liên kết với test đang chạy

Khi nhiều test chạy song song, log của nhiều thread có thể xen kẽ. Một log line nên có timestamp, level, thread name và logger để người đọc biết sự kiện đến từ đâu.

Ví dụ pattern Logback dành cho test:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level [%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

Nếu cần gắn log với test method, có thể thêm test identifier vào MDC trong JUnit extension hoặc listener, rồi đưa `%X{testId}` vào pattern. Phải xóa MDC trong `afterEach`/`finally` vì thread có thể được tái sử dụng cho test khác.

Không nên ghi toàn bộ environment variables hoặc system properties ra log. Chúng có thể chứa access token, password, private endpoint hoặc thông tin nội bộ. Chỉ ghi các giá trị không nhạy cảm cần thiết để tái hiện môi trường.

## 6. Thu thập thông tin về Spring ApplicationContext

Với lỗi Spring Test, các thông tin sau thường rất hữu ích:

- Test class và method đang load context.
- Active profiles và test property sources.
- Các context customizer hoặc initializer liên quan.
- Context cache hit/miss và việc context bị đánh dấu dirty.
- Root cause trong exception chain, đặc biệt exception đầu tiên trước các wrapper như `Failed to load ApplicationContext`.
- Bean hoặc configuration class gây lỗi dependency injection.

Khi một context fail, hãy giữ toàn bộ stack trace thay vì chỉ dòng exception cuối. Nhiều lỗi Spring được bọc qua `BeanCreationException`, `UnsatisfiedDependencyException` hoặc `ApplicationContextException`; root cause thường nằm sâu hơn trong chuỗi `Caused by`.

Không bật log DEBUG cho toàn bộ `org.springframework` ngay từ đầu nếu chưa cần. Bắt đầu với package test context hoặc bean cụ thể để giảm nhiễu, rồi mở rộng khi cần.

## 7. Giữ request/response diagnostics an toàn

Với MockMvc, WebTestClient hoặc HTTP client test, request/response có thể là bằng chứng quan trọng. Tuy nhiên, body và headers đôi khi chứa dữ liệu cá nhân, session cookie, bearer token hoặc credential.

Nên ghi các trường có ích để chẩn đoán:

- HTTP method và path (có thể bỏ query parameter nhạy cảm).
- Status code, content type và thời gian xử lý.
- Correlation ID hoặc test case ID không chứa bí mật.
- Tên header liên quan và giá trị đã redact.
- Một phần response body đã lọc khi body không chứa dữ liệu nhạy cảm.

Ví dụ minh họa log đã che token:

```text
request method=POST path=/api/orders testId=create-order-42
request header Content-Type=application/json
request header Authorization=[REDACTED]
response status=201 contentType=application/json durationMs=34
```

Không lưu nguyên `Authorization`, `Cookie`, mật khẩu, private key hoặc payload production. Nếu cần body để tái hiện, dùng dữ liệu tổng hợp và áp dụng redaction trước khi ghi file artifact.

## 8. Screenshot, video và browser evidence

Với test end-to-end chạy trình duyệt, screenshot hoặc video có thể cho thấy UI tại thời điểm lỗi. Nên chụp ảnh khi test fail hoặc ngay trước bước có thể thất bại, đặt tên theo test case và lưu trong thư mục artifact riêng.

Ví dụ cấu trúc:

```text
build/test-artifacts/
  screenshots/
    checkout-should-show-validation-error.png
  videos/
    checkout-flow.webm
  browser/
    console.log
    network-summary.json
```

Browser console và network trace có thể chứa cookie, token, URL nội bộ hoặc dữ liệu người dùng. Chỉ thu thập những gì cần thiết và che dữ liệu trước khi upload. Với screenshot, cân nhắc che thông tin cá nhân hoặc dữ liệu của tài khoản test.

Không phải mọi test backend đều cần screenshot. Chỉ bật loại bằng chứng này cho test có giao diện hoặc browser automation.

## 9. Thread dump, heap dump và JVM crash log

Khi CI bị timeout hoặc test treo, test report có thể chỉ ghi timeout mà không chỉ ra thread đang chờ ở đâu. Thread dump giúp xem stack của các thread tại thời điểm chụp.

Trong môi trường có quyền truy cập process, có thể dùng:

```bash
jcmd <pid> Thread.print
```

Hoặc:

```bash
jstack <pid>
```

Với OutOfMemoryError, JVM có thể được cấu hình tạo heap dump:

```text
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=build/test-artifacts/heapdump.hprof
```

JVM crash log có thể được ghi qua tùy chọn `-XX:ErrorFile=...` hoặc xuất hiện dưới dạng `hs_err_pid*.log`, tùy cấu hình JVM.

Thread dump và heap dump có thể lớn và chứa dữ liệu nhạy cảm như request payload, credential hoặc object state. Chỉ thu thập khi có lý do rõ ràng, giới hạn số lần chụp, kiểm soát quyền truy cập và retention. Heap dump thường không cần upload cho mọi lần chạy test.

## 10. Thu thập log của container và dịch vụ phụ trợ

Integration test có thể dùng PostgreSQL, Kafka, Redis, WireMock hoặc service được khởi chạy bằng Testcontainers. Khi test thất bại, log của test process chưa chắc giải thích được lỗi từ container.

Nên lưu:

- Container name hoặc service name và image tag/version.
- Log của container trong khoảng thời gian test chạy.
- Port mapping hoặc endpoint đã che thông tin nhạy cảm.
- Health status và thời điểm container khởi động.
- Testcontainers startup log khi lỗi xảy ra lúc tạo container.

Ví dụ lấy log container bằng Docker:

```bash
docker logs <container-name>
```

Nếu dùng Testcontainers, có thể cấu hình log consumer hoặc lấy container logs trong teardown/failure hook. Đảm bảo việc thu thập không làm thay đổi trạng thái test và không làm lộ dữ liệu xác thực của service.

## 11. Tạo thư mục artifact nhất quán

Nên gom bằng chứng do test tạo ra vào một thư mục có chủ đích, ví dụ `build/test-artifacts/`. Điều này giúp CI upload theo một pattern và tránh thu thập nhầm file từ source tree.

Ví dụ cấu trúc tổng thể:

```text
build/
  test-results/
    test/
      TEST-*.xml
  reports/
    tests/
      test/
        index.html
  test-artifacts/
    run-metadata.txt
    application.log
    screenshots/
    browser/
    containers/
    dumps/
```

Metadata nên ghi commit SHA, branch, build/run ID, attempt/retry, JDK, OS, build tool version, test task hoặc test filter và matrix dimension. Không ghi secret hoặc toàn bộ environment.

Đặt tên artifact có run ID và attempt để tránh nhầm giữa lần chạy đầu và lần retry. Nếu CI chạy matrix, thêm OS/JDK/module vào tên artifact.

## 12. Upload artifact ngay cả khi test thất bại

Đây là bước quan trọng nhất trong pipeline. Lệnh test trả exit code khác 0 thường khiến các bước sau bị bỏ qua theo mặc định. Bước upload cần dùng điều kiện luôn chạy hoặc điều kiện chạy khi job thất bại.

Ví dụ GitHub Actions với Gradle:

```yaml
name: test
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Run tests
        run: ./gradlew test

      - name: Upload test evidence
        if: ${{ always() }}
        uses: actions/upload-artifact@v4
        with:
          name: test-evidence-${{ github.run_id }}-${{ github.run_attempt }}
          path: |
            **/build/test-results/**
            **/build/reports/tests/**
            **/build/test-artifacts/**
          if-no-files-found: warn
          retention-days: 14
```

`always()` cho phép bước upload chạy sau khi bước test thất bại. Nếu chỉ muốn giữ artifact khi job thất bại, có thể dùng `if: ${{ failure() }}`. Dùng `always()` khi cần cả report của lần chạy thành công để so sánh baseline; dùng `failure()` khi muốn giảm dung lượng lưu trữ.

Ví dụ GitHub Actions với Maven:

```yaml
- name: Run Maven verification
  run: ./mvnw --batch-mode verify

- name: Upload Maven test reports
  if: ${{ always() }}
  uses: actions/upload-artifact@v4
  with:
    name: maven-test-evidence-${{ github.run_id }}-${{ github.run_attempt }}
    path: |
      **/target/surefire-reports/**
      **/target/failsafe-reports/**
      **/target/test-artifacts/**
    if-no-files-found: warn
    retention-days: 14
```

Với Maven integration test, dùng `verify` nếu Failsafe được cấu hình theo lifecycle tiêu chuẩn. Chạy `test` đơn thuần có thể chỉ thực thi Surefire và không chạy giai đoạn integration test/verify.

Nếu pipeline có nhiều job hoặc matrix, upload artifact ở job tạo ra report. Job tổng hợp có thể tải artifact từ các job con để tạo báo cáo chung, nhưng không nên đợi đến job tổng hợp mới cố truy cập thư mục build của runner khác.

## 13. Thu thập thêm diagnostics khi job thất bại hoặc timeout

Report và log thông thường nên được upload trong mọi lần chạy. Các dữ liệu nặng như thread dump, container logs hoặc heap dump có thể chỉ thu thập khi failure hoặc timeout.

Ví dụ bước diagnostics có điều kiện trong GitHub Actions:

```yaml
- name: Capture JVM diagnostics
  if: ${{ failure() }}
  shell: bash
  run: |
    mkdir -p build/test-artifacts/diagnostics
    ps -ef > build/test-artifacts/diagnostics/processes.txt
    docker ps -a > build/test-artifacts/diagnostics/containers.txt
```

Để lấy thread dump, pipeline cần biết PID của test JVM. Nếu Gradle fork test worker, PID của Gradle daemon không nhất thiết là PID của worker đang treo. Có thể cấu hình test worker ghi PID vào file metadata khi khởi động hoặc dùng cơ chế timeout của test runner để chụp dump từ đúng process.

Với job bị hủy cứng hoặc runner bị mất, bước upload cuối job có thể không chạy. Nếu loại lỗi này quan trọng, hãy dùng CI timeout hợp lý, cơ chế diagnostic trước khi kill process và log streaming tới hệ thống lưu trữ bên ngoài.

## 14. Làm cho artifact dễ tìm và dễ đọc

Một thư mục chứa hàng nghìn file không giúp nhiều nếu không biết file nào thuộc test thất bại. Hãy dùng tên ổn định và liên kết chúng với test case:

- Tên screenshot chứa class/method hoặc test ID.
- Log ghi timestamp, thread và test ID.
- Metadata ghi commit SHA, run ID và attempt.
- Report XML giữ nguyên tên testcase và failure message.
- File dump có timestamp và PID.
- Artifact name chứa module, task, OS/JDK matrix và retry nếu có.

Ví dụ metadata không nhạy cảm:

```text
commit=8f2a6c1
branch=feature/order-validation
run_id=48291
run_attempt=2
java=21
os=ubuntu-latest
build_tool=gradle
task=integrationTest
test_filter=com.example.OrderControllerIT
```

Nếu một test được retry, giữ report của từng attempt hoặc ít nhất ghi rõ attempt cuối cùng. Retry có thể làm lỗi chập chờn biến mất; report của lần đầu vẫn có giá trị để điều tra.

## 15. Retention, quyền truy cập và dữ liệu nhạy cảm

Test artifact có thể chứa dữ liệu gần với production hơn developer nghĩ. Request body, database snapshot, heap dump, browser trace và log có thể bao gồm email, token, cookie, địa chỉ hoặc thông tin khách hàng.

Áp dụng các nguyên tắc sau:

- Dùng dữ liệu tổng hợp hoặc tài khoản test chuyên dụng.
- Redact token, password, cookie, authorization header và dữ liệu cá nhân trước khi ghi artifact.
- Không upload file `.env`, private key, credential store hoặc toàn bộ thư mục home của runner.
- Hạn chế quyền đọc artifact theo quyền truy cập repository/project.
- Đặt retention phù hợp với thời gian điều tra và chính sách lưu trữ.
- Dùng retention ngắn hơn cho heap dump, database dump và browser trace có dữ liệu nhạy cảm.
- Không đưa artifact nhạy cảm vào pull request comment hoặc public build log.

Thời gian retention 14 ngày trong ví dụ chỉ là một giá trị minh họa. Dự án nên chọn thời hạn theo chính sách nội bộ, dung lượng và yêu cầu điều tra.

## 16. Khi report không được tạo hoặc bị thiếu

Không phải mọi kiểu thất bại đều tạo đủ report:

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không có JUnit XML | Test task chưa chạy, report bị tắt hoặc process bị kill quá sớm | Xác nhận task thực sự chạy và report destination được bật |
| HTML report có nhưng XML không có | Cấu hình report XML bị tắt hoặc task tùy chỉnh | Bật JUnit XML để CI đọc kết quả máy |
| Có XML nhưng thiếu log ứng dụng | Logging chỉ ghi console hoặc file log không nằm trong artifact path | Định tuyến log test vào thư mục artifact và upload thư mục đó |
| Upload step bị skip sau test failure | Step dùng điều kiện mặc định chỉ chạy khi bước trước thành công | Dùng `always()` hoặc `failure()` phù hợp |
| Artifact báo không tìm thấy file | Sai glob, khác module path hoặc report chưa được tạo | Kiểm tra working directory và path thực tế; dùng `if-no-files-found: warn` |
| Test timeout nhưng không có stack trace | Runner kill JVM trước khi report hoàn tất | Capture thread dump trước timeout hoặc tăng thời gian grace/diagnostic |
| Artifact quá lớn | Upload heap dump, video hoặc log DEBUG không giới hạn | Chỉ thu thập theo điều kiện, nén hoặc giới hạn số lượng và retention |
| Log không xác định được test nào gây ra | Nhiều test chạy song song và log thiếu thread/test ID | Thêm timestamp, thread name và test identifier |

## 17. Quy trình xử lý một CI failure

Khi job báo test thất bại, nên xử lý theo trình tự:

1. Mở JUnit XML hoặc HTML report để xác định chính xác class, method và assertion thất bại.
2. Đọc toàn bộ stack trace và tìm root cause đầu tiên, không dừng ở wrapper exception cuối.
3. Tìm log cùng timestamp/test ID để hiểu request, Spring context và service đã làm gì.
4. Nếu lỗi liên quan đến context, xem active profiles, context cache logs và bean creation chain.
5. Nếu là integration test, xem container/service logs và metadata về endpoint/port.
6. Nếu test treo hoặc timeout, xem thread dump và process diagnostics.
7. So sánh run metadata với lần chạy thành công: commit, JDK, OS, matrix, test filter và retry.
8. Tái hiện lỗi bằng cùng test filter và môi trường gần nhất có thể.

Không nên kết luận lỗi chỉ từ một dòng `Tests failed`. Hãy dùng report để xác định test, log để hiểu diễn biến và metadata để biết môi trường của lần chạy.

## 18. Ví dụ cấu hình logging và report theo profile test

Với Spring Boot, có thể tạo `src/test/resources/application-test.properties` để bật log phục vụ chẩn đoán:

```properties
logging.level.org.springframework.test.context=DEBUG
logging.level.org.springframework.test.context.cache=DEBUG
logging.level.org.springframework.boot.test.context=DEBUG
```

Test class kích hoạt profile:

```java
@SpringBootTest
@ActiveProfiles("test")
class OrderIntegrationTests {
    // Test dùng cấu hình log và bean dành cho profile test.
}
```

Trong CI, có thể thêm một bước ghi metadata vào `build/test-artifacts/run-metadata.txt` trước khi chạy test. Khi job thất bại, upload cả metadata, JUnit XML, HTML report và application log bằng một artifact duy nhất hoặc các artifact có tên liên quan.

## 19. Ghi nhớ

Để điều tra CI failure hiệu quả, cần giữ JUnit XML/HTML report, stdout/stderr, application log, Spring context diagnostics và metadata của lần chạy. Integration test hoặc UI test có thể cần thêm container logs, request/response evidence, screenshot hoặc thread dump. Đặt report vào các thư mục ổn định, upload artifact bằng điều kiện vẫn chạy sau test failure, gắn artifact với run ID/attempt và giữ retention phù hợp. Redact credential và dữ liệu cá nhân trước khi lưu. Khi có đủ report, log và metadata, developer có thể xác định test thất bại, hiểu diễn biến và tái hiện lỗi mà không phải chạy lại CI chỉ để lấy bằng chứng.


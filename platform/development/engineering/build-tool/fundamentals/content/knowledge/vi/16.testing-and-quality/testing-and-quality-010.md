# Lưu báo cáo để kiểm chứng và chẩn đoán sau khi build

Một lần build không chỉ tạo ra file JAR hoặc WAR. Quá trình build còn tạo ra bằng chứng cho biết mã nguồn đã được biên dịch và kiểm thử như thế nào: test nào đã chạy, test nào thất bại, lỗi xảy ra ở đâu, độ bao phủ mã nguồn ra sao và công cụ phân tích chất lượng đã phát hiện vấn đề gì.

Những bằng chứng đó thường được lưu thành báo cáo HTML, XML, log và các artifact chẩn đoán. Nếu chỉ xem vài dòng cuối trong terminal rồi bỏ toàn bộ thư mục báo cáo, nhóm sẽ khó điều tra lỗi xuất hiện trên CI, khó so sánh giữa các lần build và khó chứng minh một thay đổi đã được kiểm thử.

Lưu báo cáo có nghĩa là cấu hình build tool tạo đầu ra có thể kiểm tra, biết chính xác chúng nằm ở đâu, giữ lại chúng sau khi build kết thúc và cung cấp chúng cho người cần phân tích. Một quy trình tốt vẫn lưu được báo cáo khi test thất bại, bởi chính lúc đó báo cáo thường có giá trị nhất.

## 1. Báo cáo build là gì?

Báo cáo build (*build report*) là đầu ra có cấu trúc mô tả kết quả của một hoặc nhiều bước trong quá trình build. Tùy công cụ và plugin, báo cáo có thể chứa:

- Danh sách test suite, test case và trạng thái pass/fail/skip.
- Thông báo lỗi, stack trace, thời gian chạy và output của test.
- Kết quả đo độ bao phủ mã nguồn.
- Cảnh báo hoặc lỗi từ công cụ phân tích tĩnh.
- Thống kê biên dịch, kiểm tra dependency hoặc đóng gói.
- Thông tin về task, thời gian thực thi và môi trường build.

Các định dạng phổ biến:

| Định dạng | Mục đích | Đặc điểm |
|---|---|---|
| HTML | Người phát triển đọc trong trình duyệt | Có thể trình bày tổng quan, liên kết đến test và chi tiết lỗi |
| XML | CI hoặc công cụ khác xử lý tự động | Có cấu trúc ổn định hơn để nhập kết quả test và thống kê |
| JSON | Tích hợp với công cụ hoặc dashboard | Phù hợp khi plugin cung cấp schema JSON rõ ràng |
| TXT/log | Đọc nhanh và điều tra | Thường chứa thông điệp, stack trace hoặc output theo dòng |
| CSV | Phân tích dữ liệu dạng bảng | Hữu ích cho số liệu hoặc danh sách có cấu trúc nếu plugin hỗ trợ |

Không phải mọi plugin đều tạo tất cả định dạng. Hãy xem tài liệu plugin và cấu hình report tương ứng.

## 2. Phân biệt báo cáo, log và artifact build

Ba loại đầu ra này có liên quan nhưng phục vụ những mục đích khác nhau.

**Báo cáo** tóm tắt kết quả theo một cấu trúc dễ đọc hoặc dễ nhập vào hệ thống khác. Ví dụ, báo cáo test cho biết 120 test thành công, 2 test thất bại và 1 test bị bỏ qua.

**Log** ghi lại diễn biến thực thi. Log có thể chứa lệnh, thông tin task, thông báo compiler, stack trace, output do chương trình in ra và thông tin môi trường. Log thường cần thiết khi báo cáo chỉ cho biết test thất bại nhưng không giải thích nguyên nhân đầy đủ.

**Artifact build** là sản phẩm hoặc tệp được tạo ra để phân phối, triển khai hay sử dụng ở bước sau, ví dụ JAR, WAR, Docker image hoặc gói cài đặt. Báo cáo test không thay thế artifact ứng dụng và artifact ứng dụng cũng không thay thế báo cáo test.

| Đầu ra | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Test report | Test nào đã chạy và kết quả ra sao? | HTML, JUnit XML |
| Coverage report | Những dòng hoặc nhánh mã nào được thực thi? | JaCoCo HTML/XML |
| Static analysis report | Quy tắc chất lượng nào bị vi phạm? | Checkstyle, PMD, SpotBugs report |
| Build log | Task nào chạy, lệnh nào thất bại và stack trace là gì? | Log Gradle/Maven |
| Build artifact | Sản phẩm nào được tạo để phân phối? | `application.jar` |

Một lần build có thể tạo tất cả các loại đầu ra này. Cần lưu chúng theo đúng mục đích và thời gian cần sử dụng.

## 3. Vì sao phải giữ báo cáo sau khi build?

### Điều tra lỗi sau khi pipeline kết thúc

CI thường chạy trong một máy ảo hoặc container tạm thời. Khi job kết thúc, workspace có thể bị xóa. Nếu báo cáo chỉ tồn tại trong workspace đó, người phát triển sẽ không còn dữ liệu để kiểm tra.

Giữ báo cáo như artifact của job cho phép tải lại sau khi pipeline kết thúc, ngay cả khi runner đã bị thu hồi.

### Xác minh thay đổi đã được kiểm thử

Khi review một thay đổi, nhóm có thể kiểm tra báo cáo để biết test nào đã chạy, số lượng test và kết quả cụ thể. Điều này đặc biệt hữu ích khi một job có nhiều module hoặc nhiều loại test.

### So sánh giữa các lần build

Báo cáo được lưu theo commit hoặc build number giúp nhận ra xu hướng: test chạy chậm dần, số lượng test giảm, coverage thay đổi hoặc một nhóm lỗi xuất hiện thường xuyên.

### Điều tra lỗi chập chờn

Test flaky có thể chỉ thất bại trong một lần chạy. Nếu không lưu log và báo cáo của lần chạy đó, nhóm có thể không còn bằng chứng để xác định điều kiện gây lỗi.

### Cung cấp dữ liệu cho công cụ khác

Nhiều nền tảng CI, dashboard chất lượng và công cụ quản lý test có thể đọc JUnit XML hoặc định dạng báo cáo được hỗ trợ. Báo cáo có cấu trúc giúp tự động hóa việc hiển thị kết quả.

## 4. Báo cáo test trong Gradle

Với Gradle Java Plugin, task `test` sử dụng test framework và test engine đã cấu hình để chạy kiểm thử. Task `Test` mặc định tạo báo cáo HTML và kết quả XML.

Với task tên `test`, các vị trí mặc định thường gặp là:

```text
build/
├── reports/
│   └── tests/
│       └── test/
│           └── index.html
└── test-results/
    └── test/
        ├── TEST-*.xml
        └── ...
```

- `build/reports/tests/test/index.html`: báo cáo HTML để người phát triển đọc.
- `build/test-results/test/`: kết quả test dạng XML và dữ liệu liên quan.

Nếu task có tên khác, ví dụ `integrationTest`, đường dẫn report thường sử dụng tên task đó:

```text
build/reports/tests/integrationTest/index.html
build/test-results/integrationTest/
```

Đường dẫn cụ thể có thể thay đổi khi dự án cấu hình lại `reports` hoặc `binaryResultsDirectory`.

### Cấu hình báo cáo Gradle

Trong `build.gradle` (Groovy DSL):

```groovy
tasks.named('test', Test) {
    reports {
        html.required = true
        junitXml.required = true
    }
}
```

Với `build.gradle.kts` (Kotlin DSL):

```kotlin
tasks.named<Test>("test") {
    reports {
        html.required.set(true)
        junitXml.required.set(true)
    }
}
```

Hai cấu hình trên yêu cầu Gradle tạo cả báo cáo HTML và JUnit XML cho task `test`. Đây thường là lựa chọn phù hợp khi vừa cần người phát triển đọc báo cáo, vừa cần CI nhập kết quả tự động.

### Cấu hình nơi lưu báo cáo

Có thể thay đổi thư mục report:

```groovy
tasks.named('test', Test) {
    reports {
        html {
            required = true
            outputLocation = layout.buildDirectory.dir('reports/verification/unit-tests')
        }
        junitXml {
            required = true
            outputLocation = layout.buildDirectory.dir('reports/verification/junit-xml')
        }
    }
}
```

Khi đổi vị trí, cần cập nhật đường dẫn mà CI dùng để thu thập artifact. Nếu CI vẫn tìm `build/reports/tests/test/` trong khi report đã chuyển sang `build/reports/verification/unit-tests/`, artifact upload có thể không tìm thấy file.

## 5. Đọc báo cáo HTML và JUnit XML của Gradle

Báo cáo HTML thường cung cấp trang tổng quan với:

- Tổng số test.
- Số test thành công, thất bại và bị bỏ qua.
- Thời gian chạy.
- Danh sách test suite và test case.
- Chi tiết lỗi và stack trace.

JUnit XML được thiết kế để máy có thể phân tích. Một file XML thường mô tả một test suite và các test case bên trong. Hệ thống CI có thể đọc file này để hiển thị test result ngay trên giao diện pipeline.

Ví dụ cấu trúc rút gọn:

```xml
<testsuite name="com.example.OrderServiceTest"
           tests="3" failures="1" errors="0" skipped="1">
    <testcase name="createsOrder" classname="com.example.OrderServiceTest" />
    <testcase name="rejectsInvalidOrder" classname="com.example.OrderServiceTest">
        <failure message="Expected validation error">
            java.lang.AssertionError: Expected validation error
        </failure>
    </testcase>
    <testcase name="handlesLegacyOrder" classname="com.example.OrderServiceTest">
        <skipped message="Not supported in this environment" />
    </testcase>
</testsuite>
```

Đây chỉ là ví dụ cấu trúc để minh họa. XML thực tế được Gradle/Test framework tạo và có thể chứa thêm thuộc tính, thời gian, output hoặc phần tử mở rộng.

Không nên chỉnh sửa trực tiếp XML do test task tạo. Hãy xem nó là bằng chứng đầu ra của lần chạy. Nếu cần một định dạng khác, tạo bước chuyển đổi riêng để giữ nguyên báo cáo gốc.

## 6. Lưu log kiểm thử trong Gradle

Báo cáo HTML và XML không phải lúc nào cũng chứa toàn bộ output mà test in ra. Có thể cấu hình `testLogging` để Gradle hiển thị những sự kiện cần thiết trong console:

```groovy
tasks.named('test', Test) {
    testLogging {
        events 'passed', 'skipped', 'failed'
        exceptionFormat 'full'
        showStandardStreams = true
    }
}
```

Các thiết lập này giúp log console hiển thị test đã pass, skip, fail, stack trace đầy đủ và standard output/error của test.

Trong Kotlin DSL:

```kotlin
tasks.named<Test>("test") {
    testLogging {
        events("passed", "skipped", "failed")
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
        showStandardStreams = true
    }
}
```

Không phải dự án nào cũng nên bật `showStandardStreams = true` cho toàn bộ test. Nếu test in nhiều dữ liệu, log có thể rất lớn và làm khó tìm thông tin quan trọng. Có thể bật tạm khi điều tra hoặc chỉ cho một nhóm test cần thiết.

### Tăng mức chi tiết của Gradle

Các tùy chọn dòng lệnh hữu ích:

```bash
./gradlew test --stacktrace
./gradlew test --info
```

- `--stacktrace` hiển thị stack trace khi build thất bại.
- `--info` tăng mức chi tiết log để hiểu task và quá trình thực thi.

`--debug` tạo log rất chi tiết. Log debug có thể chứa đường dẫn, thuộc tính môi trường hoặc dữ liệu nhạy cảm tùy plugin và build logic. Chỉ nên dùng khi cần, hạn chế quyền truy cập và kiểm tra nội dung trước khi chia sẻ ra ngoài.

## 7. Báo cáo test trong Maven Surefire

Maven Surefire Plugin chạy unit test trong giai đoạn `test` của lifecycle. Theo cấu hình mặc định phổ biến, báo cáo được lưu trong:

```text
target/surefire-reports/
├── TEST-com.example.OrderServiceTest.xml
├── com.example.OrderServiceTest.txt
└── ...
```

- File `TEST-*.xml` chứa kết quả test theo định dạng XML tương thích với nhiều hệ thống CI.
- File `.txt` thường chứa output hoặc thông tin chi tiết phục vụ điều tra.

Khi một test thất bại, Surefire thường vẫn tạo báo cáo của test đã chạy trước khi Maven kết thúc với trạng thái thất bại. Vì vậy, CI cần thu thập `target/surefire-reports/` ngay cả khi lệnh Maven trả về mã lỗi.

### Cấu hình Surefire

Ví dụ cấu hình trong `pom.xml`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.2</version>
            <configuration>
                <reportsDirectory>${project.build.directory}/surefire-reports</reportsDirectory>
                <printSummary>true</printSummary>
                <trimStackTrace>false</trimStackTrace>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Ví dụ này chỉ định rõ thư mục báo cáo và yêu cầu giữ stack trace đầy đủ trong phần báo cáo theo cấu hình plugin. Phiên bản plugin cần được chọn theo chính sách tương thích của dự án.

Nếu thay đổi `reportsDirectory`, phải cập nhật đường dẫn artifact mà CI thu thập.

### Chạy test và xem báo cáo

```bash
mvn test
```

Sau khi lệnh kết thúc, mở các file trong `target/surefire-reports/`. Nếu Maven build thất bại do test assertion, hãy xem XML và TXT để biết test case nào thất bại và stack trace tương ứng.

Để xem dependency hoặc plugin configuration không phải mục tiêu của Surefire report; hãy dùng các lệnh chẩn đoán riêng như `mvn help:effective-pom` khi cần xác định cấu hình plugin hiệu lực.

## 8. Báo cáo integration test trong Maven Failsafe

Unit test và integration test thường có vòng đời khác nhau. Maven Failsafe Plugin được thiết kế để chạy integration test ở các phase `integration-test` và `verify`.

Báo cáo thường nằm trong:

```text
target/failsafe-reports/
├── TEST-com.example.OrderApiIT.xml
├── com.example.OrderApiIT.txt
└── ...
```

Một cấu hình điển hình:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.2</version>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Chạy:

```bash
mvn verify
```

`verify` chạy các phase trước đó trong lifecycle, bao gồm integration test và bước kiểm tra kết quả của Failsafe. Đây là cách gọi thông thường để bảo đảm lỗi integration test được phản ánh ở cuối quy trình.

Failsafe được thiết kế để cho phép các bước teardown hoặc post-integration-test chạy trước khi kết luận build thất bại do test. Vì vậy, khi điều tra integration test, cần xem cả log và `target/failsafe-reports/`.

## 9. Báo cáo coverage với JaCoCo

Test report cho biết test nào chạy và kết quả ra sao. Nó không tự trả lời mã nguồn được thực thi đến mức nào. Để đo coverage, dự án Java thường dùng JaCoCo.

JaCoCo có thể tạo báo cáo HTML và XML. HTML phù hợp để người phát triển xem package, class, method, line và branch coverage. XML thường được công cụ CI hoặc hệ thống phân tích chất lượng nhập vào.

### Cấu hình JaCoCo trong Gradle

```groovy
plugins {
    id 'java'
    id 'jacoco'
}

tasks.test {
    finalizedBy(tasks.jacocoTestReport)
}

tasks.jacocoTestReport {
    dependsOn(tasks.test)
    reports {
        html.required = true
        xml.required = true
    }
}
```

Với cấu hình mặc định thường gặp, báo cáo được tạo tại:

```text
build/reports/jacoco/test/html/index.html
build/reports/jacoco/test/jacocoTestReport.xml
```

`test` chạy trước và `jacocoTestReport` sử dụng dữ liệu thực thi để tạo báo cáo. `finalizedBy` giúp report task được thực thi sau task test trong quy trình được cấu hình; `dependsOn` thể hiện report task cần kết quả test.

Trong dự án thực tế, hãy kiểm tra task graph và cấu hình hiện có để tránh tạo dependency cycle hoặc chạy report không cần thiết. Nếu test thất bại, cần xác nhận task report có được thực thi và dữ liệu execution có được tạo hay không.

### Cấu hình JaCoCo trong Maven

Maven JaCoCo Plugin thường được cấu hình với goal `prepare-agent` để gắn Java agent khi test chạy, sau đó goal `report` tạo báo cáo:

```xml
<plugin>
    <groupId>org.jacoco</groupId>
    <artifactId>jacoco-maven-plugin</artifactId>
    <version>0.8.12</version>
    <executions>
        <execution>
            <goals>
                <goal>prepare-agent</goal>
            </goals>
        </execution>
        <execution>
            <id>report</id>
            <phase>verify</phase>
            <goals>
                <goal>report</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Báo cáo thường nằm trong:

```text
target/site/jacoco/index.html
target/site/jacoco/jacoco.xml
```

Phiên bản plugin trong ví dụ cần được điều chỉnh theo JDK và dependency policy của dự án.

### Coverage không đồng nghĩa với chất lượng

Coverage cao không chứng minh test có assertion tốt hoặc mọi trường hợp biên đã được kiểm tra. Một dòng code có thể được chạy nhưng không có assertion xác nhận kết quả đúng. Vì vậy, hãy xem coverage cùng test report, chất lượng assertion và các kiểm tra khác.

## 10. Báo cáo từ static analysis và công cụ chất lượng

Ngoài test và coverage, build có thể tạo báo cáo từ các công cụ:

- Checkstyle: vi phạm coding style và quy tắc định dạng.
- PMD: các mẫu code có nguy cơ hoặc khó bảo trì.
- SpotBugs: phát hiện một số lỗi tiềm ẩn từ bytecode.
- Error Prone: kiểm tra bổ sung trong quá trình biên dịch.
- Dependency analysis: dependency không dùng, dependency dư thừa hoặc vấn đề version.

Đường dẫn báo cáo phụ thuộc plugin, task, module và cấu hình. Ví dụ một plugin có thể ghi HTML vào `build/reports/checkstyle/` hoặc XML vào một thư mục khác. Không nên hardcode một đường dẫn dựa trên giả định; hãy đọc cấu hình task/report hoặc log để biết vị trí thực tế.

Khi CI cần nhập báo cáo, ưu tiên định dạng máy đọc được mà plugin cung cấp. Đồng thời lưu HTML để người phát triển có thể mở chi tiết. Một số công cụ cần cả file dữ liệu trung gian và report; nếu chỉ upload HTML, dữ liệu gốc phục vụ tái tạo có thể bị mất.

## 11. Báo cáo trong build nhiều module

Trong build nhiều module, mỗi module có thể chạy test và tạo report riêng:

```text
commerce/
├── app/
│   └── build/reports/tests/test/index.html
├── domain/
│   └── build/reports/tests/test/index.html
└── infrastructure/
    └── build/reports/tests/test/index.html
```

Nếu CI chỉ thu thập `app/build/reports/`, kết quả của `domain` và `infrastructure` sẽ bị bỏ sót. Hãy cấu hình artifact path để bao gồm tất cả module, hoặc tạo báo cáo tổng hợp.

### Báo cáo tổng hợp trong Gradle

Gradle có plugin `test-report-aggregation` để tổng hợp kết quả test từ các project tham gia. Plugin này phù hợp với build multi-project khi cần một trang báo cáo chung thay vì yêu cầu người xem mở từng module.

Việc cấu hình phụ thuộc vào quan hệ project, test suite và plugin đã áp dụng. Hãy khai báo các project cần tổng hợp theo mô hình aggregation của Gradle và kiểm tra task report được tạo. Báo cáo tổng hợp nên bổ sung khả năng điều hướng, không thay thế việc lưu XML gốc của từng task nếu CI hoặc công cụ khác cần chúng.

### Báo cáo tổng hợp trong Maven

Maven reactor chạy các module trong một lần build, nhưng báo cáo Surefire/Failsafe thường vẫn được tạo trong từng module. Có thể dùng plugin báo cáo hoặc cơ chế CI để tổng hợp các XML từ mọi module.

Khi tổng hợp, cần giữ thông tin module trong tên hoặc metadata báo cáo để không nhầm hai test có cùng tên ở các module khác nhau. Cũng cần tránh chỉ giữ báo cáo tổng hợp mà xóa báo cáo gốc khi nhóm cần điều tra chi tiết.

## 12. Lưu báo cáo ngay cả khi build thất bại

Đây là một yêu cầu quan trọng khi thiết kế pipeline. Nếu bước upload artifact chỉ chạy khi build thành công, các báo cáo có giá trị nhất có thể bị mất đúng lúc test thất bại.

CI nên có hai phần độc lập:

1. Chạy build và ghi nhận exit code.
2. Thu thập log/report/artifact chẩn đoán với điều kiện luôn chạy, kể cả khi bước build thất bại hoặc bị hủy theo cách nền tảng hỗ trợ.

Ví dụ khái quát:

```text
Checkout source
      |
      v
Setup JDK and build tool
      |
      v
Run build and tests
      |
      +---- success or failure
      |
      v
Collect reports and logs (always)
      |
      v
Upload artifacts
      |
      v
Publish final job status
```

Trong GitHub Actions, có thể dùng `if: always()` cho bước upload artifact:

```yaml
- name: Run tests
  run: ./gradlew test

- name: Upload test reports
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: test-reports
    path: |
      **/build/reports/tests/**
      **/build/test-results/**
    if-no-files-found: warn
    retention-days: 14
```

Ví dụ này minh họa cách thu thập báo cáo Gradle trong GitHub Actions. Với Maven, thay các đường dẫn bằng `**/target/surefire-reports/**` và `**/target/failsafe-reports/**`. Cú pháp và giới hạn retention cần tuân theo nền tảng CI đang sử dụng.

`if: always()` giúp bước upload được xem xét chạy ngay cả khi bước trước thất bại. Tuy nhiên, nếu job bị hủy cứng, runner mất kết nối hoặc nền tảng không còn khả năng thực thi bước sau, upload vẫn có thể không hoàn tất. Vì vậy, cần kiểm tra kết quả upload và trạng thái artifact thực tế.

## 13. Chọn đường dẫn artifact rõ ràng

Một lỗi thường gặp là CI upload sai thư mục vì build tool dùng output directory khác dự kiến.

Ví dụ Gradle:

```text
build/reports/tests/test/index.html
build/test-results/test/TEST-*.xml
build/reports/jacoco/test/html/index.html
build/reports/jacoco/test/jacocoTestReport.xml
```

Ví dụ Maven:

```text
target/surefire-reports/TEST-*.xml
target/failsafe-reports/TEST-*.xml
target/site/jacoco/index.html
target/site/jacoco/jacoco.xml
```

Các đường dẫn trên là mặc định thường gặp; cấu hình project hoặc plugin có thể thay đổi chúng. Khi pipeline không tìm thấy report:

- Xem log task để biết task có thực sự chạy không.
- Kiểm tra output directory của task/plugin.
- Xác nhận tên task hoặc module.
- Kiểm tra pattern glob của CI.
- Xem report có bị xóa bởi `clean` hoặc bước cleanup sau build không.

Không nên dùng pattern quá rộng như upload toàn bộ workspace nếu không cần. Nó có thể đưa cả file cache, dữ liệu lớn hoặc thông tin không nên chia sẻ vào artifact.

## 14. Lưu log có thể tái hiện và chẩn đoán

Report thường cho biết điều gì thất bại; log giúp hiểu tại sao. Để log hữu ích, cần giữ ngữ cảnh:

- Commit SHA hoặc source revision.
- Build number hoặc pipeline run ID.
- Phiên bản JDK và vendor.
- Phiên bản Gradle/Maven và plugin quan trọng.
- Hệ điều hành hoặc container image.
- Lệnh build và tham số được dùng.
- Module/task thất bại.
- Thời điểm bắt đầu/kết thúc và exit code.

Không cần ghi toàn bộ thông tin máy nếu không liên quan. Hãy lưu những yếu tố có thể ảnh hưởng đến kết quả hoặc giúp tái tạo lỗi.

### Log Gradle

```bash
./gradlew test --stacktrace --info
```

`--stacktrace` giúp xem nguyên nhân lỗi; `--info` cung cấp thêm thông tin quá trình chạy. Nếu cần log chi tiết hơn, dùng `--debug` có kiểm soát và kiểm tra nội dung trước khi lưu hoặc chia sẻ.

### Log Maven

```bash
mvn test -e
```

`-e` hiển thị stack trace lỗi. Maven có `-X` để bật debug output:

```bash
mvn test -X
```

Debug output có thể rất dài và tùy plugin có thể chứa giá trị thuộc tính hoặc đường dẫn nhạy cảm. Không upload log debug công khai nếu chưa kiểm tra và redaction.

## 15. Bảo vệ thông tin nhạy cảm trong báo cáo và log

Báo cáo và log có thể chứa nhiều dữ liệu hơn dự kiến:

- URL có token hoặc query parameter nhạy cảm.
- Tên người dùng, email hoặc dữ liệu khách hàng trong test fixture.
- Đường dẫn nội bộ và tên máy.
- Biến môi trường hoặc cấu hình dịch vụ.
- Thông tin xác thực do test in ra khi thất bại.

Trước khi lưu artifact ở nơi nhiều người có thể truy cập, cần xác định quyền truy cập và thời hạn lưu. Không đưa password, access token, private key hoặc dữ liệu cá nhân thật vào log. Test nên dùng dữ liệu giả lập hoặc đã ẩn danh.

Nếu cần debug một lần chạy, hãy redaction log trước khi chia sẻ bên ngoài phạm vi nhóm. Việc đặt artifact ở chế độ private không thay thế nguyên tắc không ghi bí mật vào log.

## 16. Chính sách retention và dung lượng

Giữ báo cáo vô thời hạn có thể làm tăng dung lượng lưu trữ và chi phí. Không phải mọi loại artifact cần cùng thời hạn.

Một chính sách tham khảo:

| Loại dữ liệu | Thời hạn tham khảo | Lý do |
|---|---|---|
| Test report của pull request | 7–14 ngày | Đủ thời gian review và điều tra lỗi gần nhất |
| Report của release build | Theo chính sách phát hành | Có thể cần đối chiếu với phiên bản đã phát hành |
| Log debug chi tiết | Ngắn hơn log thông thường | Dung lượng lớn và có thể chứa dữ liệu nhạy cảm |
| Coverage report theo nhánh | Theo nhu cầu xu hướng chất lượng | Cần so sánh qua nhiều lần build |
| Build artifact phát hành | Theo chính sách artifact/release | Phục vụ triển khai, rollback hoặc kiểm toán |

Các con số là ví dụ để bắt đầu thảo luận, không phải tiêu chuẩn chung. Tổ chức cần xác định thời hạn theo yêu cầu vận hành, chi phí, bảo mật và quy định lưu trữ.

Nên phân biệt artifact tạm của pull request với artifact phát hành. Có thể giữ report PR ngắn ngày, nhưng giữ report và artifact release lâu hơn để phục vụ truy vết.

## 17. Báo cáo khi test không chạy hoặc build thất bại sớm

Không phải lần build thất bại nào cũng tạo test report.

Ví dụ:

| Điểm thất bại | Có thể có test report? | Nơi điều tra trước |
|---|---|---|
| Dependency resolution thất bại | Không, test task chưa chạy | Build log, repository và dependency resolution |
| Compile thất bại | Thường không có report test cho task chưa chạy | Compiler output, source file và toolchain |
| Test assertion thất bại | Có, nếu test task đã chạy và report được tạo | HTML/XML test report và test log |
| Test process bị crash | Có thể có report một phần hoặc không đầy đủ | Test worker log, process exit và CI log |
| Job bị hủy trước khi upload | Report có thể còn trong workspace nhưng chưa được lưu bên ngoài | Runner/job cancellation và artifact step |
| Report task thất bại | Có thể có dữ liệu test nhưng thiếu report cuối | Log của report task và dữ liệu trung gian |

Khi CI báo không tìm thấy report, đừng lập tức kết luận plugin bị lỗi. Hãy xác định task tạo report có chạy hay chưa. Nếu build dừng ở bước compile, không có test report là kết quả bình thường.

## 18. Phân biệt test report và test result

Một test task có thể tạo dữ liệu kết quả trung gian, sau đó một report task dùng dữ liệu đó để tạo HTML hoặc XML. Nếu chỉ upload HTML, có thể thiếu dữ liệu gốc mà một công cụ tổng hợp cần. Nếu chỉ upload XML, người phát triển vẫn có thể cần HTML để điều hướng và đọc nhanh.

Với Gradle, `Test` task có các thuộc tính liên quan đến reports và binary results. Với Maven, Surefire/Failsafe ghi report theo cấu hình plugin. Hãy giữ cả:

- Báo cáo dễ đọc cho người.
- Kết quả có cấu trúc để CI nhập.
- Log phục vụ chẩn đoán.
- Dữ liệu coverage hoặc analysis khi cần.

Không phải dự án nào cũng cần mọi loại đầu ra cho mọi job. Hãy chọn dựa trên câu hỏi cần trả lời và chi phí lưu trữ.

## 19. Tự động hóa việc thu thập report trong Gradle

Trong build nhiều module, có thể gom các report vào một vị trí dễ thu thập. Tuy nhiên, không nên copy thủ công mọi thứ sau mỗi task nếu Gradle đã có report aggregation hoặc plugin cung cấp output provider.

Nếu cần một task đóng gói báo cáo để CI tải về, hãy khai báo input từ output của các task report và output riêng cho archive. Ví dụ ý tưởng:

```groovy
tasks.register('packageVerificationReports', Zip) {
    from(layout.buildDirectory.dir('reports'))
    from(layout.buildDirectory.dir('test-results'))
    archiveFileName = 'verification-reports.zip'
    destinationDirectory = layout.buildDirectory.dir('distributions')
}
```

Đây là ví dụ đơn giản trong một project. Trong multi-project, cần lấy output từ từng subproject hoặc dùng report aggregation; không giả định mọi report đều nằm dưới build directory của root project.

Nếu task đóng gói chạy trong pipeline, cần bảo đảm các task test/report đã hoàn thành trước. Dùng dependency rõ ràng tới các task tạo report hoặc cấu trúc lifecycle phù hợp, thay vì dựa vào thứ tự tình cờ.

## 20. Điều tra một test thất bại bằng báo cáo

Giả sử CI báo task `:orders:test` thất bại. Một quy trình điều tra:

1. Mở `orders/build/reports/tests/test/index.html` để xem tổng quan.
2. Tìm test case thất bại và đọc assertion message.
3. Mở chi tiết stack trace để xác định dòng mã và nguyên nhân.
4. Kiểm tra XML tương ứng trong `orders/build/test-results/test/` nếu cần dữ liệu máy đọc hoặc tích hợp CI.
5. Đọc log task/test worker để tìm output trước khi lỗi xảy ra.
6. Ghi nhận commit, JDK, Gradle version và lệnh chạy.
7. Tái hiện test cụ thể hoặc test suite trong môi trường tương đương.
8. Sau khi sửa, chạy lại và so sánh report mới với report của lần lỗi.

Nếu lỗi chỉ xuất hiện trong CI, hãy giữ cả report lẫn môi trường chạy. Một test có thể phụ thuộc timezone, locale, filesystem case sensitivity, thứ tự test, port, biến môi trường hoặc dữ liệu bên ngoài. Report đơn lẻ có thể không đủ để tái hiện nếu không có ngữ cảnh môi trường.

## 21. Điều tra test flaky

Test flaky là test có lúc pass, lúc fail trong điều kiện tưởng như giống nhau. Báo cáo và log của từng lần chạy là bằng chứng cần thiết để so sánh.

Hãy lưu:

- Test name và test suite.
- Timestamp và build/run ID.
- Số lần retry nếu framework hoặc plugin hỗ trợ.
- Stack trace và assertion message.
- Output của test trước khi thất bại.
- Phiên bản JDK, OS và cấu hình chạy.
- Thông tin về parallel test execution nếu có.

Không nên chỉ lưu kết quả cuối sau retry. Nếu test fail lần đầu rồi pass lần hai, trạng thái cuối có thể là success nhưng lần fail ban đầu vẫn là tín hiệu quan trọng. Hãy kiểm tra plugin/framework có xuất thông tin retry và cấu hình CI có giữ được report của các lần chạy đó không.

## 22. Báo cáo và bằng chứng cho một bản phát hành

Với release build, nên liên kết báo cáo với chính artifact được phát hành. Một tập bằng chứng có thể gồm:

```text
release-1.4.0/
├── application.jar
├── build-info.txt
├── test-reports/
│   ├── unit-tests.xml
│   └── integration-tests.xml
├── coverage/
│   ├── index.html
│   └── jacoco.xml
└── logs/
    └── build.log
```

`build-info.txt` có thể ghi commit SHA, build number, JDK, build tool version và thời điểm tạo. Cần bảo đảm thông tin này không chứa secret.

Lưu báo cáo cùng metadata của artifact giúp nhóm trả lời: artifact này được tạo từ commit nào, bằng môi trường nào và đã qua những kiểm thử nào. Hệ thống phát hành có thể lưu báo cáo riêng nhưng cần có liên kết rõ đến version hoặc digest của artifact.

## 23. Những lỗi thường gặp khi lưu báo cáo

| Vấn đề | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| CI không tìm thấy HTML report | Sai glob hoặc output directory đã được đổi | Kiểm tra cấu hình report và đường dẫn thực tế |
| Test fail nhưng không có report | Test task chưa chạy, process bị crash hoặc report task không hoàn tất | Kiểm tra log và trạng thái task |
| Report chỉ có một module | Artifact path chỉ trỏ đến một build directory | Thu thập mọi module hoặc tạo report tổng hợp |
| Upload chỉ chạy khi build success | Bước upload không có điều kiện chạy khi failure | Dùng cơ chế always/always-run của CI |
| XML được upload nhưng CI không hiển thị test | Sai định dạng hoặc pattern không khớp | Kiểm tra schema và đường dẫn XML |
| Report cũ bị dùng nhầm | Workspace tái sử dụng và output chưa được dọn | Làm sạch output có kiểm soát hoặc phân biệt theo build run |
| Log quá lớn | Bật standard streams/debug cho mọi test | Giới hạn mức log và chỉ bật chi tiết khi cần |
| Artifact chứa secret | Test hoặc plugin in cấu hình nhạy cảm | Redact, dùng dữ liệu giả và giới hạn quyền truy cập |
| Không so sánh được các lần build | Thiếu commit/build metadata hoặc retention quá ngắn | Lưu metadata và đặt retention phù hợp |

## 24. Quy trình thiết lập lưu báo cáo cho dự án mới

Khi thiết lập build cho dự án, có thể thực hiện theo thứ tự:

1. Xác định các bước cần bằng chứng: unit test, integration test, coverage, static analysis và build log.
2. Bật report HTML để người phát triển xem và XML/định dạng máy đọc được cho CI.
3. Xác nhận output directory thực tế của từng task và từng module.
4. Chạy một lần thành công để kiểm tra report được tạo và có dữ liệu.
5. Chạy một trường hợp test thất bại có kiểm soát để xác nhận report vẫn được tạo.
6. Cấu hình CI thu thập report ngay cả khi build thất bại.
7. Kiểm tra artifact tải về có đủ file, mở được HTML và XML có thể được CI nhận diện.
8. Đặt retention theo loại artifact và mức độ cần lưu.
9. Kiểm tra log/report không chứa secret hoặc dữ liệu thật nhạy cảm.
10. Ghi lại commit, JDK, build tool và build run ID để hỗ trợ tái hiện.

## 25. Checklist khi chẩn đoán sau build

Khi một build hoàn thành hoặc thất bại, hãy xác định:

- Build dừng ở dependency resolution, compilation, test hay report task?
- Task tạo report có thực sự chạy không?
- HTML và XML được lưu ở thư mục nào?
- CI đã upload artifact khi job thất bại chưa?
- Có report của tất cả module và tất cả test suite không?
- Log có stack trace và output cần thiết không?
- Coverage/static analysis report có tương ứng cùng commit và build run không?
- Có metadata về JDK, build tool, OS và commit SHA không?
- Artifact có bị xóa hoặc ghi đè bởi build run khác không?
- Quyền truy cập và thời hạn lưu có phù hợp không?

Lưu báo cáo sau build giúp kết quả kiểm thử và chất lượng trở thành bằng chứng có thể kiểm tra lại. Gradle và Maven đều tạo được báo cáo test ở các thư mục mặc định; JaCoCo và các plugin phân tích bổ sung bằng chứng về coverage và chất lượng. Khi CI luôn thu thập những đầu ra này, kể cả khi build thất bại, nhóm có thể điều tra lỗi dựa trên dữ liệu thực tế thay vì chỉ dựa vào một thông báo cuối cùng trong terminal.

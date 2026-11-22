# Đọc `failsafe-reports` và đối chiếu kết quả với unit test trong Maven

## 1. Bài toán: `BUILD FAILURE` xảy ra ở lớp kiểm thử nào?

Trong một dự án Maven, hai nhóm kiểm thử thường được tổ chức riêng:

- **Unit tests**: kiểm tra hành vi của thành phần nhỏ, thường chạy trong phase `test` bằng **Maven Surefire Plugin**.
- **Integration tests (IT)**: kiểm tra sự phối hợp nhiều thành phần, file system, database, HTTP service hoặc môi trường triển khai, thường chạy trong phase `integration-test` bằng **Maven Failsafe Plugin** và được xác minh ở phase `verify`.

Giả sử terminal xuất hiện:

~~~text
[INFO] Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
...
[ERROR] There are test failures.
[INFO] BUILD FAILURE
~~~

Một dòng `Tests run` không đủ trả lời: những test nào vừa chạy, nhóm unit hay integration bị lỗi, lỗi thuộc assertion hay exception, và liệu Failsafe đã được xác minh ở `verify` chưa.

Maven tách báo cáo mặc định thành hai thư mục:

~~~text
target/surefire-reports/   # Unit tests: Maven Surefire Plugin
target/failsafe-reports/   # Integration tests: Maven Failsafe Plugin
~~~

Bài Knowledge này thuộc nhóm **Kiểm thử tích hợp**, tập trung vào việc **đọc, giải thích và đối chiếu báo cáo** — không chỉ thuộc lòng tên hai plugin.

Sau bài học, bạn có thể:

1. Biết report nào đến từ Surefire, report nào đến từ Failsafe.
2. Đọc `*.txt`, `TEST-*.xml` và `failsafe-summary.xml` đúng mục đích.
3. Giải thích `tests`, `failures`, `errors`, `skipped`, `time`, stack trace và testcase identity.
4. Phân biệt lỗi unit test làm build dừng sớm với lỗi integration test được Failsafe ghi lại và kiểm tra ở `verify`.
5. Biết vì sao `mvn integration-test` không nên là lệnh hoàn thiện một integration-test lifecycle.
6. Chạy dự án Java 17/JUnit 5 có **unit tests và integration tests thực sự**, so báo cáo của cả hai.
7. Cố ý tạo một IT failure để quan sát log, XML, summary và exit status của Maven.
8. Tổng hợp kết quả trong multi-module/CI mà không cộng nhầm báo cáo cũ, reruns hoặc suites trùng lặp.
9. Xử lý các tình huống “không có report”, test bị skip, suite không được discover và test flaky.

**Giới hạn phạm vi:** Maven 3.x, Java 17 và Surefire/Failsafe Plugin phiên bản `3.5.4` trong ví dụ. Tên file, định dạng XML, thông số và cách báo cáo có thể thay đổi nếu project dùng plugin/report extensions khác. Các log/PID/thời gian hiển thị trong bài là **minh họa** trừ những dòng stdout có đánh dấu “chính xác”.

## 2. Surefire và Failsafe khác nhau ở chỗ nào?

| Tiêu chí | Maven Surefire Plugin | Maven Failsafe Plugin |
| --- | --- | --- |
| Nhóm kiểm thử chính | Unit test | Integration test |
| Goal chính | `surefire:test` | `failsafe:integration-test` và `failsafe:verify` |
| Phase thường dùng | `test` | `integration-test` và `verify` |
| Thư mục report mặc định | `target/surefire-reports` | `target/failsafe-reports` |
| Report theo test class | `TEST-*.xml` và `*.txt` | `TEST-*.xml` và `*.txt` |
| File summary bổ sung | Không có `failsafe-summary.xml` tương đương bắt buộc | `failsafe-summary.xml` |
| Xử lý test failure | Thông thường dừng build ở `test` nếu không ignore | Ghi kết quả tại `integration-test`, kiểm tra và có thể fail build tại `verify` |
| Naming convention mặc định | `Test*.java`, `*Test.java`, `*Tests.java`, `*TestCase.java` | `IT*.java`, `*IT.java`, `*ITCase.java` |

Đây là **mặc định thường gặp**. Project có thể tùy chỉnh includes/excludes, report directory, test provider và executions; không lấy tên file làm bằng chứng tuyệt đối về loại kiểm thử nếu POM thật đã thay chính sách.

### Vì sao Failsafe cần goal `verify`?

Integration test có thể cần một dịch vụ được khởi động ở `pre-integration-test` và phải dừng ở `post-integration-test`. Nếu một test thất bại mà build dừng ngay tại `integration-test`, service có thể chưa được cleanup.

Failsafe được thiết kế để ghi nhận IT results tại `failsafe:integration-test` nhưng **không biến assertion failure thành lỗi build ngay ở phase này**. Sau đó lifecycle có cơ hội chạy `post-integration-test`, rồi goal `failsafe:verify` kiểm tra kết quả và trả build failure nếu cần.

~~~text
validate → compile → test (Surefire)
                │
                ▼
             package
                │
                ▼
        pre-integration-test
                │
                ▼
        integration-test (Failsafe chạy IT, ghi report)
                │
                ▼
        post-integration-test (cleanup nếu được bind)
                │
                ▼
        verify (Failsafe đọc summary để quyết định PASS/FAIL)
~~~

**Lệnh nên chạy khi muốn thực hiện đầy đủ integration tests:**

~~~bash
mvn clean verify
~~~

Không dùng `mvn integration-test` như kết luận “IT đã được kiểm chứng đầy đủ” trong quy trình có setup/cleanup, vì lệnh đó không chạy các phase phía sau là `post-integration-test` và `verify`. Lệnh `verify` đi qua cả hai.

**Ngoại lệ cần biết:** nếu unit test thất bại trước phase integration-test, build có thể dừng tại Surefire và **không có báo cáo Failsafe** ở lần chạy hiện tại. Điều đó không có nghĩa integration tests đã PASS.

## 3. Đọc đúng cấu trúc thư mục báo cáo

Với một module đã chạy đầy đủ và có hai lớp unit test cùng hai lớp IT, cây đầu ra có thể trông như:

~~~text
target/
├── surefire-reports/
│   ├── demo.PriceCalculatorTest.txt
│   ├── demo.ReceiptIdsTest.txt
│   ├── TEST-demo.PriceCalculatorTest.xml
│   └── TEST-demo.ReceiptIdsTest.xml
└── failsafe-reports/
    ├── demo.ReceiptFlowIT.txt
    ├── demo.ReceiptGateIT.txt
    ├── TEST-demo.ReceiptFlowIT.xml
    ├── TEST-demo.ReceiptGateIT.xml
    └── failsafe-summary.xml
~~~

Đây là cấu trúc **dự kiến cho dự án thực hành**; plugin có thể còn sinh file output/debug khác, đặc biệt khi fork JVM bất thường.

### Nên đọc file nào trước?

1. **`*.txt`**: đọc nhanh số test và thông báo lỗi theo **test class**, hữu ích cho con người.
2. **`TEST-*.xml`**: kết quả có cấu trúc để CI phân tích, gồm suite counts và từng testcase.
3. **`failsafe-summary.xml`**: Failsafe tổng hợp kết quả IT để `failsafe:verify` sử dụng.
4. **Console log + exit code**: xác nhận Maven đã chạy tới phase nào và build PASS/FAIL.
5. **`*.dump`/`*.dumpstream` nếu có**: hỗ trợ tìm vấn đề fork/crash/communication; không phải test-report thông thường.

Đọc theo thứ tự này để tránh lỗi: nhìn thấy một file `TEST-*.xml` chứa ba test PASS rồi kết luận toàn bộ build PASS, trong khi một suite khác có failure hoặc goal `verify` chưa chạy.

### Thư mục có thể bị tùy chỉnh

Nếu plugin khai báo `<reportsDirectory>` hoặc Maven build directory khác mặc định, report không nhất thiết ở `target/failsafe-reports` hay `target/surefire-reports`. Có thể tìm cấu hình thực bằng:

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
~~~

Trong multi-module Maven, **mỗi module thường có `target/` riêng**. Đừng chỉ đọc `target` ở aggregator root rồi kết luận tất cả modules không có report.

## 4. Cách đọc file `*.txt`

Một report kiểu text có thể chứa:

~~~text
-------------------------------------------------------------------------------
Test set: demo.ReceiptFlowIT
-------------------------------------------------------------------------------
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0, Time elapsed: 0.037 s -- in demo.ReceiptFlowIT
~~~

Đây là **dòng minh họa**, thời gian và định dạng dấu phân cách phụ thuộc plugin/reporter.

Các trường quan trọng:

| Trường | Ý nghĩa |
| --- | --- |
| `Test set` | Test suite/class mà báo cáo đại diện. |
| `Tests run` | Số testcase được reporter ghi nhận trong test set. |
| `Failures` | Thường là assertion thất bại, ví dụ `assertEquals` không đạt. |
| `Errors` | Exception hoặc lỗi thực thi test ngoài loại assertion failure được reporter phân loại. |
| `Skipped` | Test được đánh dấu không chạy/không thực thi theo điều kiện framework hoặc cơ chế skip. |
| `Time elapsed` | Thời lượng thực thi theo reporter; không nhất thiết là toàn thời gian build. |

Trong nhiều báo cáo, một test bị skip vẫn nằm trong tổng `tests`; do đó có thể tính gần đúng (khi không có đặc biệt như retry/flake):

~~~text
passed = tests - failures - errors - skipped
~~~

Tuy nhiên **không tự động xem công thức này là chuẩn tuyệt đối** cho mọi provider và chế độ rerun: báo cáo có thể lưu nhiều lần thử, `flakyFailure`/`flakyError` hoặc testsuite aggregation đặc biệt. Khi số liệu quan trọng, đọc cả XML và cấu hình rerun.

### `Failures` và `Errors` khác nhau

Ví dụ assertion không đạt:

~~~java
assertEquals(42, actual);
~~~

Nếu `actual=41`, JUnit có thể ném `org.opentest4j.AssertionFailedError`; test reporter thường ghi vào `failures`.

Ví dụ exception không dự kiến:

~~~java
int amount = Integer.parseInt("invalid");
~~~

Nếu không được test xử lý hoặc mong đợi, reporter thường ghi vào `errors`. Loại lỗi phân loại theo framework/plugin và exception cụ thể; không quyết định hoàn toàn bằng việc test có ném exception hay không. `assertThrows` có thể biến một ngoại lệ **được mong đợi** thành test PASS.

### Stack trace giúp khoanh vùng

Khi fail, file `*.txt` có thể chứa tên test method, message và stack trace. Hãy:

1. Tìm **test method cụ thể**.
2. Đọc dòng assertion/exception đầu tiên có ý nghĩa.
3. Xác định lỗi từ application code, test fixture, mock, filesystem hay external service.
4. Đọc `Caused by` nếu có để tìm nguyên nhân gốc.
5. So với XML của **chính test class đó**, tránh đọc nhầm unit report thành IT report.

## 5. Cách đọc `TEST-*.xml`

XML có cấu trúc phù hợp với Jenkins, GitLab, GitHub Actions và công cụ CI sử dụng JUnit-style reports.

Ví dụ giản lược cho **một suite PASS**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="demo.ReceiptFlowIT"
           tests="2"
           errors="0"
           failures="0"
           skipped="0"
           time="0.037">
    <testcase name="checkoutCreatesReadableReceipt"
              classname="demo.ReceiptFlowIT"
              time="0.023"/>
    <testcase name="invalidReceiptIdIsRejected"
              classname="demo.ReceiptFlowIT"
              time="0.014"/>
</testsuite>
~~~

Đây là **XML minh họa hợp lệ ở mức tối thiểu**, không phải bản sao nguyên văn do plugin sẽ phát hành. Report thật có thể có `timestamp`, `hostname`, `properties`, `system-out` và các trường khác.

### Ý nghĩa các phần tử/thuộc tính

- `<testsuite>`: thường đại diện một class/test set; thuộc tính `tests` là số testcase được reporter tính.
- `name`: tên suite/test set.
- `time`: thời lượng, thông thường tính bằng **giây** và có thể là số thập phân.
- `<testcase>`: một test case/method được báo cáo, có `name`, `classname`, `time`.
- `<failure>`: assertion failure, có thể chứa message, type và stack trace.
- `<error>`: exception hoặc lỗi ngoài assertion failure.
- `<skipped>`: lý do bỏ qua test nếu có.
- `<system-out>` / `<system-err>`: output tiêu chuẩn của test khi reporter ghi.
- `<properties>`: thông tin môi trường/JVM properties nếu reporter ghi; **có thể chứa dữ liệu nhạy cảm**.

Một testcase thất bại thường có dạng:

~~~xml
<testcase name="gateRejectsRequestedFailure"
          classname="demo.ReceiptGateIT"
          time="0.008">
    <failure message="Deliberate IT failure requested"
             type="org.opentest4j.AssertionFailedError">
        AssertionFailedError: Deliberate IT failure requested
    </failure>
</testcase>
~~~

Chỉ là **mẫu minh họa** để đọc ý nghĩa `<failure>`. Stack trace và message thực tế có thể gồm nhiều dòng, vị trí source code và cú pháp khác.

### Không cộng nhầm testcase trong XML

Khi tổng hợp kết quả:

- Lấy **mỗi report XML thuộc đúng module, đúng suite** một lần.
- Tránh cộng cả số `tests` trên `<testsuite>` **và** đếm `<testcase>` của cùng suite — làm vậy sẽ nhân đôi.
- Nếu CI đã xuất một báo cáo aggregate, đừng cộng lại cả aggregate và report module.
- Nếu có rerun/flaky reporting, cần hiểu `flakyFailure`/`flakyError`, `rerunFailure` và policy của CI.
- Không xem `0 failures` trong một XML là thành công nếu các XML khác của cùng module có error/failure.

## 6. `failsafe-summary.xml`: báo cáo dành cho bước `verify`

Failsafe thường ghi:

~~~text
target/failsafe-reports/failsafe-summary.xml
~~~

File này **khác** các `TEST-*.xml`. Các TEST XML ghi chi tiết testcase để con người/CI phân tích; `failsafe-summary.xml` là **tóm tắt điều hành của Failsafe**, được `failsafe:verify` sử dụng.

Một cấu trúc minh họa:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<failsafe-summary result="0" timeout="false">
    <completed>3</completed>
    <errors>0</errors>
    <failures>0</failures>
    <skipped>0</skipped>
    <flakes>0</flakes>
</failsafe-summary>
~~~

Đây là **ví dụ về các trường**, không yêu cầu file thật có đúng thứ tự, chính xác từng thuộc tính hoặc chỉ gồm năm thẻ. Một số phiên bản có metadata/schema declaration bổ sung và `failureMessage` khi cần.

### Các trường cần hiểu

| Trường | Vai trò |
| --- | --- |
| `completed` | Số lần thực thi testcase hoàn tất được Failsafe tổng kết theo model của plugin, không phải tên class. |
| `errors` | Số test error được tổng hợp. |
| `failures` | Số assertion failure được tổng hợp. |
| `skipped` | Số test bị skip. |
| `flakes` (nếu có) | Thông tin các bài test flaky theo reporter/version. |
| `result`, `timeout` | Trạng thái điều hành nội bộ của Failsafe, phải giải nghĩa theo đúng schema/version. |

**Không dùng một giá trị `result` bất kỳ làm “PASS/FAIL tự chế” nếu chưa kiểm tra tài liệu phiên bản.** `failsafe:verify` là thành phần hiểu file summary và quyết định lỗi build.

Nếu summary không tồn tại, có thể là:

- IT goal chưa chạy vì chỉ gọi `mvn test`.
- Build đã dừng sớm tại unit test/compile.
- Failsafe executions chưa được bind vào lifecycle.
- Plugin skip theo cấu hình.
- Đường dẫn báo cáo bị tùy chỉnh.
- Plugin/fork gặp lỗi nghiêm trọng trước khi tạo summary.
- Bạn đang xem sai module hoặc artifact cũ.

**Không kết luận “không có summary = integration tests PASS”.** Trong CI, việc không tìm thấy report mà vẫn muốn đảm bảo test đã chạy nên được coi là tình huống cần điều tra.

## 7. Đối chiếu hai thư mục: cùng đơn vị, khác mục tiêu

Một bảng so sánh kết quả sau `mvn clean verify`:

| Nhóm | Thư mục | Classes | Tests | Failures | Errors | Skipped | Kết luận ví dụ |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Unit | `surefire-reports` | 2 | 3 | 0 | 0 | 0 | PASS |
| Integration | `failsafe-reports` | 2 | 3 | 0 | 0 | 0 | PASS, sau `failsafe:verify` |

Đây là **số liệu mục tiêu của project thực hành**, không phải giá trị cố định của dự án khác.

### Đọc đúng ý nghĩa so sánh

1. **Không trộn lẫn nội dung:** cùng các trường `tests/failures/errors/skipped` nhưng unit test và IT kiểm tra các cấp khác nhau.
2. **Không thay một nhóm bằng nhóm kia:** ba unit tests PASS không chứng minh end-to-end flow có thể ghi file, đọc file hoặc kết nối service.
3. **Không chỉ cộng `tests`:** số test ít hơn mong đợi có thể là discovery lỗi, skip, đổi pattern hoặc build dừng trước IT.
4. **Đọc testcase identity:** một lỗi trong `ReceiptGateIT` cần so với chức năng/fixture integration, không phải tự động đổ lỗi cho `PriceCalculatorTest`.
5. **Đọc trạng thái Maven:** Failsafe IT result chưa được goal `verify` xử lý thì chưa phải trạng thái cuối của integration-test lifecycle.
6. **Nhìn phạm vi/module:** các report được tạo bởi module nào, POM nào, version plugin nào, run nào?

### Phân biệt số lượng lớp và số lượng phương thức test

Một file `TEST-demo.ReceiptFlowIT.xml` có thể chứa **hai testcase**. Do đó:

~~~text
2 report XML files ≠ 2 test methods
~~~

Với demo, Surefire tạo hai report XML, tổng cộng **ba methods**; Failsafe cũng tạo hai report XML, tổng cộng **ba methods**. Hãy cộng `tests` của suites, không dùng số lượng file làm số lượng tests.

## 8. Dự án thực hành Java 17 + JUnit 5

Ta xây một project đơn module, không cần DB server. Integration tests vẫn kiểm tra **sự phối hợp của nhiều thành phần và filesystem thật** trong thư mục tạm do JUnit quản lý.

### 8.1. Cây thư mục

~~~text
failsafe-reports-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── demo/
    │           ├── PriceCalculator.java
    │           ├── ReceiptIds.java
    │           ├── ReceiptRepository.java
    │           └── CheckoutService.java
    └── test/
        └── java/
            └── demo/
                ├── PriceCalculatorTest.java
                ├── ReceiptIdsTest.java
                ├── ReceiptFlowIT.java
                └── ReceiptGateIT.java
~~~

Hai lớp `*Test` là unit tests; hai lớp `*IT` là integration tests theo default naming conventions. Cả hai nhóm có thể nằm trong `src/test/java` và đều được biên dịch tại `test-compile`; **khác biệt là plugin nào chọn và chạy chúng ở phase nào**, không bắt buộc phải có một source directory `src/integration-test/java` riêng.

### 8.2. POM đầy đủ

Tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>failsafe-reports-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <demo.failIT>false</demo.failIT>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.5.4</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                    <systemPropertyVariables>
                        <demo.failIT>${demo.failIT}</demo.failIT>
                    </systemPropertyVariables>
                </configuration>
                <executions>
                    <execution>
                        <id>run-integration-tests</id>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Vì sao POM dùng cấu hình này?**

- `maven.compiler.release=17` yêu cầu bytecode tương thích Java 17.
- `junit-jupiter` mang JUnit Jupiter API/engine vào test scope.
- Surefire 3.5.4 xử lý lớp test đặt tên `*Test` ở phase `test`.
- Failsafe 3.5.4 có hai goal `integration-test` và `verify`; chúng được bind theo default phases tương ứng thông qua `<execution>`.
- `failIfNoTests=true` giúp **nhận diện lỗi không phát hiện test** thay vì lặng lẽ tuyên bố pass khi một plugin không tìm thấy test nào.
- `demo.failIT=false` là công tắc riêng của project demo, không phải một tham số built-in của Failsafe.
- `systemPropertyVariables` truyền giá trị property này vào **JVM chạy IT**, nơi `Boolean.getBoolean("demo.failIT")` đọc nó.
- Compiler/JAR Plugin được ghim version để demo bớt phụ thuộc Maven defaults.
- Không khai báo điều kiện chạy dựa vào clock, mạng hay database thật; các tests có thể tái hiện trên máy có JDK 17, Maven phù hợp và quyền tải dependencies.

**Lưu ý về tên goals:** viết `<goal>integration-test</goal>` và `<goal>verify</goal>` trong execution Failsafe; chạy `mvn clean verify` để hai goal được thực thi đúng phases. Chỉ khai báo plugin mà không bind goals vào lifecycle không đảm bảo IT sẽ chạy.

### 8.3. Main class: tính tiền đơn hàng

Tạo `src/main/java/demo/PriceCalculator.java`:

~~~java
package demo;

public final class PriceCalculator {
    private PriceCalculator() {
    }

    public static int total(int quantity, int unitPrice) {
        if (quantity < 0 || unitPrice < 0) {
            throw new IllegalArgumentException(
                    "Quantity and unit price must be non-negative");
        }
        return Math.multiplyExact(quantity, unitPrice);
    }
}
~~~

Hàm pure này dễ test độc lập: với `quantity=3` và `unitPrice=14`, kết quả là `42`. Giá trị âm bị từ chối; integer overflow được Java xử lý qua `Math.multiplyExact`.

### 8.4. Main class: kiểm tra ID hóa đơn

Tạo `src/main/java/demo/ReceiptIds.java`:

~~~java
package demo;

public final class ReceiptIds {
    private ReceiptIds() {
    }

    public static String requireValid(String receiptId) {
        if (receiptId == null
                || !receiptId.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid receipt ID");
        }
        return receiptId;
    }
}
~~~

Rule đơn giản chỉ nhận chữ Latin, số, underscore và dấu gạch nối; chặn `../` để tránh traversal khi dùng tên file. Đây là kiểm tra ID **cho demo**, không thay thế toàn bộ threat model của một ứng dụng nhận đường dẫn người dùng.

### 8.5. Main class: repository ghi/đọc file thật

Tạo `src/main/java/demo/ReceiptRepository.java`:

~~~java
package demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

public final class ReceiptRepository {
    private final Path directory;

    public ReceiptRepository(Path directory) {
        this.directory = Objects.requireNonNull(directory);
    }

    public Path save(String receiptId, int amount) throws IOException {
        String id = ReceiptIds.requireValid(receiptId);
        Files.createDirectories(directory);
        Path receiptFile = directory.resolve(id + ".txt");
        Files.writeString(
                receiptFile,
                Integer.toString(amount),
                StandardCharsets.UTF_8);
        return receiptFile;
    }

    public int load(String receiptId) throws IOException {
        String id = ReceiptIds.requireValid(receiptId);
        Path receiptFile = directory.resolve(id + ".txt");
        return Integer.parseInt(
                Files.readString(
                        receiptFile, StandardCharsets.UTF_8).trim());
    }
}
~~~

Class dùng Java 17 standard library và thực hiện file I/O thật. IT sẽ dùng `@TempDir` để cô lập file giữa các test cases, tránh ghi vào thư mục production hoặc đường dẫn cố định.

### 8.6. Main class: checkout kết hợp tính tiền và lưu hóa đơn

Tạo `src/main/java/demo/CheckoutService.java`:

~~~java
package demo;

import java.io.IOException;
import java.util.Objects;

public final class CheckoutService {
    private final ReceiptRepository repository;

    public CheckoutService(ReceiptRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public int checkout(
            String receiptId, int quantity, int unitPrice)
            throws IOException {
        int amount = PriceCalculator.total(quantity, unitPrice);
        repository.save(receiptId, amount);
        return amount;
    }
}
~~~

Integration test sẽ kiểm tra chuỗi **CheckoutService → PriceCalculator → ReceiptRepository → filesystem**, khác với unit test một hàm tính toán.

## 9. Unit tests: `*Test.java` chạy bằng Surefire

### 9.1. `PriceCalculatorTest.java` — hai methods

Tạo `src/test/java/demo/PriceCalculatorTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceCalculatorTest {
    @Test
    void calculatesTotal() {
        assertEquals(42, PriceCalculator.total(3, 14));
    }

    @Test
    void rejectsNegativeQuantity() {
        assertThrows(
                IllegalArgumentException.class,
                () -> PriceCalculator.total(-1, 14));
    }
}
~~~

### 9.2. `ReceiptIdsTest.java` — một method

Tạo `src/test/java/demo/ReceiptIdsTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;

class ReceiptIdsTest {
    @Test
    void rejectsPathTraversal() {
        assertThrows(
                IllegalArgumentException.class,
                () -> ReceiptIds.requireValid("../unsafe"));
    }
}
~~~

**Unit test totals:** `PriceCalculatorTest` có hai methods, `ReceiptIdsTest` có một → **3 test methods**, không có dependency on filesystem/network. Theo Surefire default includes, hai lớp `*Test` này thuộc unit test set.

Chạy:

~~~bash
mvn clean test
~~~

Khi thành công, bạn dự kiến tìm:

~~~text
target/surefire-reports/TEST-demo.PriceCalculatorTest.xml
target/surefire-reports/TEST-demo.ReceiptIdsTest.xml
~~~

Vì `clean test` dừng ở phase `test`, Failsafe goal ở `integration-test` **chưa được chạy**. Sau clean build, việc chưa có `target/failsafe-reports` là **bình thường** đối với lệnh này.

## 10. Integration tests: `*IT.java` chạy bằng Failsafe

### 10.1. `ReceiptFlowIT.java` — hai methods

Tạo `src/test/java/demo/ReceiptFlowIT.java`:

~~~java
package demo;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReceiptFlowIT {
    @TempDir
    Path tempDirectory;

    @Test
    void checkoutCreatesReadableReceipt() throws IOException {
        ReceiptRepository repository =
                new ReceiptRepository(tempDirectory);
        CheckoutService service = new CheckoutService(repository);

        int amount = service.checkout("order-1", 3, 14);

        assertEquals(42, amount);
        assertEquals(42, repository.load("order-1"));
        assertTrue(Files.exists(tempDirectory.resolve("order-1.txt")));
    }

    @Test
    void invalidReceiptIdIsRejected() {
        ReceiptRepository repository =
                new ReceiptRepository(tempDirectory);
        CheckoutService service = new CheckoutService(repository);

        assertThrows(
                IllegalArgumentException.class,
                () -> service.checkout("../unsafe", 1, 7));
        assertFalse(Files.exists(tempDirectory.resolve("unsafe.txt")));
    }
}
~~~

Đây là integration test ở quy mô nhỏ: nó phối hợp các class ứng dụng và **filesystem thật**; `@TempDir` giữ dữ liệu test tách biệt. Không cần Docker hay server HTTP chỉ để hiểu report. Trong hệ thống thật, IT có thể chạy REST API, database, message queue hoặc một tiến trình ứng dụng.

### 10.2. `ReceiptGateIT.java` — một method có công tắc tạo failure

Tạo `src/test/java/demo/ReceiptGateIT.java`:

~~~java
package demo;

import java.io.IOException;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class ReceiptGateIT {
    @TempDir
    Path tempDirectory;

    @Test
    void gateRejectsRequestedFailure() throws IOException {
        ReceiptRepository repository =
                new ReceiptRepository(tempDirectory);
        CheckoutService service = new CheckoutService(repository);

        assertEquals(12, service.checkout("gate", 2, 6));
        assertEquals(12, repository.load("gate"));

        assertFalse(
                Boolean.getBoolean("demo.failIT"),
                "Deliberate IT failure requested");
    }
}
~~~

Khi Maven property `demo.failIT=false` (mặc định của POM), test PASS. Khi chạy Maven với `-Ddemo.failIT=true`, property được Failsafe truyền vào test JVM qua `systemPropertyVariables`, assertion cuối **cố ý fail**. Các unit tests **không đọc công tắc này**, vì vậy vẫn PASS. Bài dùng công tắc để minh họa lỗi báo cáo, không đưa hành vi “ép test fail bằng property” vào hệ thống production.

### 10.3. Vì sao không có IT trong Surefire report?

Với naming conventions mặc định:

~~~text
PriceCalculatorTest.java -> Surefire
ReceiptIdsTest.java      -> Surefire
ReceiptFlowIT.java       -> Failsafe
ReceiptGateIT.java       -> Failsafe
~~~

Đây là những **Java classes nằm chung `src/test/java`**, được Maven test-compile biên dịch, nhưng các plugin chọn những class khác nhau theo pattern.

Nếu project tùy chỉnh `<includes>`/`<excludes>`, hoặc dùng tên như `MyIntegrationTest.java` mà không cấu hình Failsafe tương ứng, điều đó có thể thay đổi. **Không coi hậu tố `IT` là một “annotation bắt buộc” của JUnit**; nó chỉ là naming convention mà Failsafe có thể dùng để discover class.

## 11. Thực hành A — chỉ chạy unit tests

Trong project root, xác nhận môi trường:

~~~bash
mvn --version
java -version
~~~

Sau đó:

~~~bash
mvn clean test
~~~

Với POM và code ở trên, kỳ vọng:

- Surefire tìm `PriceCalculatorTest` và `ReceiptIdsTest`.
- Tổng **3 unit test methods PASS**, `0 failures, 0 errors, 0 skipped`.
- Maven kết thúc `BUILD SUCCESS` nếu không có vấn đề môi trường.
- `target/surefire-reports` chứa hai report XML và hai file text.
- `target/failsafe-reports` **chưa được sinh bởi lượt clean test**, vì Failsafe IT/verify goals chưa tới phase của chúng.

Ví dụ tổng hợp console:

~~~text
[INFO] Running demo.PriceCalculatorTest
[INFO] Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
[INFO] Running demo.ReceiptIdsTest
[INFO] Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
[INFO] Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
[INFO] BUILD SUCCESS
~~~

Đây là **log minh họa**; plugin có thể in thêm goal header, thời gian, test class order và thông tin môi trường. Dòng `Tests run: 3` là tổng unit tests của demo, không phải unit + IT.

### Đọc report theo lớp

Mở:

~~~text
target/surefire-reports/demo.PriceCalculatorTest.txt
target/surefire-reports/demo.ReceiptIdsTest.txt
~~~

Nếu mỗi file cho `Failures=0, Errors=0`, bạn biết **hai unit test classes được báo cáo PASS**. Nhưng nếu một file khác trong cùng thư mục có error, kết luận toàn module vẫn chưa PASS.

## 12. Thực hành B — chạy đầy đủ unit tests và integration tests

Chạy:

~~~bash
mvn clean verify
~~~

Kỳ vọng:

- Surefire ở `test`: **3 unit methods PASS**.
- Failsafe ở `integration-test`: **3 integration methods PASS**.
- Failsafe `verify` xác nhận report summary hợp lệ và không có failure/error.
- Maven kết thúc `BUILD SUCCESS`.

Cây report được rút gọn:

~~~text
target/
├── surefire-reports/
│   ├── TEST-demo.PriceCalculatorTest.xml       # 2 tests
│   ├── TEST-demo.ReceiptIdsTest.xml             # 1 test
│   ├── demo.PriceCalculatorTest.txt
│   └── demo.ReceiptIdsTest.txt
└── failsafe-reports/
    ├── TEST-demo.ReceiptFlowIT.xml              # 2 tests
    ├── TEST-demo.ReceiptGateIT.xml              # 1 test
    ├── demo.ReceiptFlowIT.txt
    ├── demo.ReceiptGateIT.txt
    └── failsafe-summary.xml
~~~

Bảng đối chiếu:

| Nguồn | Classes | Tests | Failures | Errors | Skipped | PASS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Surefire | 2 | 3 | 0 | 0 | 0 | 3 |
| Failsafe | 2 | 3 | 0 | 0 | 0 | 3 |
| Tổng riêng cho demo | 4 | 6 | 0 | 0 | 0 | 6 |

**Không dùng bảng “tổng” để thay cho từng nhóm ở CI.** Một dự án có unit=PASS nhưng IT=FAIL cần hiển thị rõ nhóm nào không đạt; cộng lại thành một số tổng không cho biết ranh giới lỗi.

### Kiểm tra `failsafe-summary.xml`

Sau `mvn clean verify` thành công, trong file summary có thể thấy các giá trị ý nghĩa tương đương:

~~~text
completed = 3
failures  = 0
errors    = 0
skipped   = 0
~~~

Những số này là **kỳ vọng của demo với ba IT methods**, không phải yêu cầu mọi implementation luôn in đúng những dòng plain text. Report thật là XML; có thể có thuộc tính, `flakes` và các trường khác theo version.

Hãy đọc cùng báo cáo `TEST-demo.ReceiptFlowIT.xml` và `TEST-demo.ReceiptGateIT.xml`. Summary là căn cứ tổng hợp của Failsafe; test XML giúp biết **ai** chạy và nếu fail thì **vì sao**.

## 13. Thực hành C — cố ý làm integration test thất bại

Tạo một lượt chạy sạch với công tắc:

~~~bash
mvn -Ddemo.failIT=true clean verify
~~~

Với POM demo:

- Surefire vẫn chạy **3 unit methods PASS**.
- `ReceiptFlowIT` vẫn có **2 methods PASS**.
- `ReceiptGateIT` có **1 assertion failure** vì `Boolean.getBoolean("demo.failIT")` là true.
- Failsafe ghi report ở phase `integration-test`.
- Khi lifecycle tới `verify`, Failsafe đánh giá summary và Maven **BUILD FAILURE** (exit status khác 0).

Đây là **failure có chủ đích**, không phải lỗi Java hay cấu hình trong demo.

Một bảng report sau lượt này:

| Nguồn | Tests | Failures | Errors | Skipped | Nhận định |
| --- | ---: | ---: | ---: | ---: | --- |
| Surefire | 3 | 0 | 0 | 0 | Unit PASS |
| Failsafe | 3 | 1 | 0 | 0 | IT FAIL |
| Maven cuối cùng | — | — | — | — | Build FAIL tại `failsafe:verify` |

### File nào chứa lỗi?

File liên quan:

~~~text
target/failsafe-reports/demo.ReceiptGateIT.txt
target/failsafe-reports/TEST-demo.ReceiptGateIT.xml
target/failsafe-reports/failsafe-summary.xml
~~~

Trong file XML của lớp `ReceiptGateIT`, tìm testcase `gateRejectsRequestedFailure` và phần tử `<failure>`. Reporter thường ghi message:

~~~text
Deliberate IT failure requested
~~~

Cùng lúc, XML của `ReceiptFlowIT` có `failures=0`, unit reports vẫn PASS.

**Dấu hiệu chẩn đoán:** failure không nằm trong `target/surefire-reports`. Nếu bạn chỉ nhìn unit report, bạn sẽ bỏ sót nguyên nhân build failure. Cần ghi nhận trạng thái cả hai loại report.

### Vì sao `failsafe:integration-test` không dừng ngay?

Failsafe không fail build tức thời khi assertion IT thất bại, để có thể chạy cleanup tại `post-integration-test`. Goal `failsafe:verify` mới đọc summary và quyết định thất bại. Dự án demo không khởi động server cần cleanup, nhưng ranh giới lifecycle vẫn minh họa nguyên tắc.

**Không diễn giải rộng thành “mọi lỗi runtime ở integration-test đều cho phép build tiếp”.** Nếu plugin không tải được, JVM crash, POM lỗi hoặc xảy ra lỗi build khác, lifecycle có thể dừng sớm. Failsafe hoãn **kết quả test failure theo cơ chế của nó**, không bảo đảm mọi lỗi đều được nuốt tới `verify`.

### Quay lại trạng thái PASS

Chạy:

~~~bash
mvn clean verify
~~~

Vì POM mặc định `demo.failIT=false`, lỗi có chủ đích biến mất. Xác minh báo cáo mới; **đừng đưa report của lượt fail trước vào phép cộng** sau khi đã clean build.

## 14. Hình dung testcase-level report cho hai lượt chạy

Giả sử ba IT methods của demo:

| Testcase | Khi mặc định | Khi `-Ddemo.failIT=true` |
| --- | --- | --- |
| `ReceiptFlowIT.checkoutCreatesReadableReceipt` | PASS | PASS |
| `ReceiptFlowIT.invalidReceiptIdIsRejected` | PASS | PASS |
| `ReceiptGateIT.gateRejectsRequestedFailure` | PASS | FAIL (assertion) |

Khi so XML, cần đối chiếu ít nhất:

1. `classname` và `name` của testcase, không chỉ số đếm.
2. Element `<failure>`, `<error>` hoặc `<skipped>`.
3. Test class nằm trong Surefire hay Failsafe report.
4. Thời điểm/lượt build để tránh XML cũ.
5. Maven có chạy `failsafe:verify` hay không.

Các số `time` có thể khác mỗi lần build; PID, thứ tự test, JVM startup và tốc độ I/O không cố định. Đừng viết assertion “suite time phải bằng 0.025” chỉ vì XML ví dụ có một giá trị thời gian.

## 15. Cách đọc báo cáo trên Linux, macOS và Windows

Bạn không cần cài phần mềm đặc biệt để xem file XML/text. Nếu đang trong project root:

**Linux/macOS (Bash):**

~~~bash
find target/surefire-reports -type f -name 'TEST-*.xml' -print
find target/failsafe-reports -type f -name 'TEST-*.xml' -print
cat target/failsafe-reports/failsafe-summary.xml
~~~

Các lệnh `find` trên chỉ dùng được sau khi thư mục được tạo. Nếu thiếu directory sau `mvn clean test` thì đó là một trạng thái bình thường vì IT chưa chạy.

**Windows PowerShell:**

~~~powershell
Get-ChildItem "target\surefire-reports" -Filter "TEST-*.xml"
Get-ChildItem "target\failsafe-reports" -Filter "TEST-*.xml"
Get-Content "target\failsafe-reports\failsafe-summary.xml"
~~~

PowerShell sẽ báo lỗi nếu đường dẫn không có; hãy xác nhận đã thực thi `mvn clean verify` thành công hoặc IT failure có tạo report.

**Kiểm tra nhanh text report:**

~~~bash
cat target/failsafe-reports/demo.ReceiptGateIT.txt
~~~

hoặc:

~~~powershell
Get-Content "target\failsafe-reports\demo.ReceiptGateIT.txt"
~~~

### Không dùng mỗi `grep` để tổng hợp số liệu từ XML

Một report XML có thể xuống dòng, có namespaces hoặc định dạng khác; regex đơn giản trên text dễ bỏ sót. Nếu cần số liệu CI, nên dùng parser XML đúng nghĩa hoặc chức năng test-report của CI, không parse XML như log line-by-line.

## 16. Ví dụ script Python 3 để so sánh các XML reports

Vì nhiệm vụ là **đọc và đối chiếu**, một tiện ích nhỏ dùng thư viện chuẩn Python 3 có thể giúp kiểm tra tổng `tests/failures/errors/skipped` của từng nhóm sau build. Nếu không cài Python, bạn vẫn có thể đọc thủ công `*.txt` và XML trong IDE; project Java 17 ở trên **không phụ thuộc script này** để chạy.

Tạo file `compare_reports.py` trong root của dự án:

~~~python
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


def suite_counts(directory: Path):
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    reports = sorted(directory.glob("TEST-*.xml"))

    if not reports:
        raise RuntimeError(f"No TEST-*.xml files in {directory}")

    for report in reports:
        root = ET.parse(report).getroot()
        root_name = root.tag.rsplit("}", 1)[-1]

        if root_name != "testsuite":
            raise RuntimeError(
                f"Unexpected XML root in {report}: {root_name}")

        for key in totals:
            totals[key] += int(root.attrib.get(key, "0"))

    totals["passed"] = (
        totals["tests"] - totals["failures"]
        - totals["errors"] - totals["skipped"]
    )
    return len(reports), totals


def main():
    for label, directory in (
        ("Unit", Path("target/surefire-reports")),
        ("Integration", Path("target/failsafe-reports")),
    ):
        count, summary = suite_counts(directory)
        print(
            f"{label}: report_files={count}, "
            f"tests={summary['tests']}, "
            f"passed={summary['passed']}, "
            f"failures={summary['failures']}, "
            f"errors={summary['errors']}, "
            f"skipped={summary['skipped']}"
        )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, ET.ParseError, RuntimeError) as error:
        print(f"Report analysis failed: {error}", file=sys.stderr)
        sys.exit(2)
~~~

Sau khi chạy:

~~~bash
mvn clean verify
python3 compare_reports.py
~~~

**Stdout chính xác của script cho dự án mẫu khi PASS** (giả định mỗi class sinh một file `TEST-*.xml` như cấu hình mặc định):

~~~text
Unit: report_files=2, tests=3, passed=3, failures=0, errors=0, skipped=0
Integration: report_files=2, tests=3, passed=3, failures=0, errors=0, skipped=0
~~~

Với Windows nếu Python được cài dưới launcher:

~~~powershell
py -3 compare_reports.py
~~~

Lưu ý script là **công cụ học tập cho XML report chuẩn có root `testsuite`**. Nó **cố ý thất bại** nếu thiếu reports hoặc root XML không như dự kiến; không tự diễn giải một thư mục trống thành PASS. Trong CI tổng quát, có thể gặp XML namespaces, nested suites, flaky reruns, test-report extensions hoặc aggregate reports; cần mở rộng parser và chính sách đếm theo schema/plugin version thật.

### Script không thay thế `failsafe:verify`

Ngay cả khi script in `failures=0, errors=0`, nó không tự chứng minh goal Failsafe `verify` đã chạy, không chứng minh integration environment đã cleanup và không xử lý mọi trạng thái nội bộ của `failsafe-summary.xml`. CI nên dùng **Maven exit status cùng báo cáo gốc**; script là bước hỗ trợ phân tích.

### Nếu integration test được cố ý fail

Sau:

~~~bash
mvn -Ddemo.failIT=true clean verify
python3 compare_reports.py
~~~

Maven sẽ trả lỗi ở `verify` nhưng report vẫn có thể được tạo. Script có thể in:

~~~text
Unit: report_files=2, tests=3, passed=3, failures=0, errors=0, skipped=0
Integration: report_files=2, tests=3, passed=2, failures=1, errors=0, skipped=0
~~~

Đây là kỳ vọng minh họa khi report counts theo project mẫu, không phải lời khẳng định nội dung của các file chưa được chạy thực tế trong mọi môi trường. Cần phân biệt **script đọc report** với **lệnh Maven trước đó đã thất bại đúng như thiết kế**.

## 17. Khi nào báo cáo có thể bị đọc sai?

### 17.1. Report cũ còn trong `target`

Nếu chạy `mvn verify` không `clean` nhiều lần, có thể còn file report từ test class đã bị đổi tên/xóa hoặc từ một lần chạy trước, tùy plugin/report cleanup behavior. Khi so sánh chính xác test counts sau khi thay naming/configuration, dùng:

~~~bash
mvn clean verify
~~~

Trong CI, lưu artifact report của **đúng build ID/commit/module**, không trộn với report từ các lần chạy khác.

### 17.2. Unit test fail trước khi Failsafe chạy

Nếu Surefire phát hiện failure ở phase `test`, Maven thường dừng build sớm. Bạn có thể chỉ thấy `surefire-reports` và **không thấy `failsafe-reports`** trong fresh build. Đây là “IT NOT RUN”, **không phải “IT PASS”**.

### 17.3. Báo cáo XML thiếu nhưng console có log

Có thể XML reporting đã bị disable/tùy biến, report path đổi, plugin crash trước khi ghi hoặc dự án dùng report extension khác. Kiểm tra:

- Effective POM và plugin versions.
- `reportsDirectory`/reporter configuration.
- Log phase và goal thực sự chạy.
- Sự tồn tại của `failsafe-summary.xml`.
- Lỗi fork VM hoặc test provider.

Không tạo một file XML giả chỉ để CI thấy “đã có report”.

### 17.4. Test classes không khớp naming convention

Ví dụ class `CheckoutIntegrationTest.java` không mặc định được Failsafe xem là `*IT.java` nếu POM không thêm includes tương ứng. Nếu nó vẫn được Surefire chọn do `*Test.java`, test có thể chạy ở phase khác với mong muốn.

Có thể khai báo includes/excludes tường minh trong plugin config, chẳng hạn:

~~~xml
<configuration>
    <includes>
        <include>**/*IT.java</include>
    </includes>
</configuration>
~~~

Đây là **mảnh cấu hình của Failsafe**, không phải POM hoàn chỉnh cần chèn vào demo. Nếu có test classes mang tên khác, điều chỉnh patterns cho phù hợp; không copy lại các mặc định một cách máy móc.

### 17.5. Test bị skip hoặc no tests found

- Test framework có thể dùng `@Disabled` để skip một method.
- Surefire/Failsafe có các tham số skip tests riêng, ví dụ `skipITs` dành cho integration tests.
- `-Dmaven.test.skip=true` còn ảnh hưởng việc compile test sources theo quy tắc Maven/plugin.
- `failIfNoTests` mặc định có thể không làm build fail khi không phát hiện test; demo đặt true ở cả hai plugins nhằm bắt trường hợp không có tests.

Một build in `BUILD SUCCESS` sau khi **mọi IT đều bị skip** không phải bằng chứng integration behavior đã được xác nhận. CI cần check số tests được thực thi và test policy của project.

### 17.6. Flaky reruns

Surefire/Failsafe có thể cấu hình rerun failing tests. Khi một attempt fail nhưng một attempt sau PASS, report có thể chứa các phần tử liên quan `flakyFailure`/`flakyError` và thống kê khác. Một bộ test nhìn chung PASS nhưng có flakes vẫn cần điều tra.

**Không cộng mỗi `<failure>` hay `<testcase>` thô mà chưa biết schema và retry policy**. Nhiều CI systems có thể hiển thị pass cuối cùng nhưng vẫn lưu lịch sử failed attempts.

### 17.7. Failsafe summary không giống tổng unit + IT

`failsafe-summary.xml` mô tả **kết quả Failsafe integration-test execution**, không phải tổng mọi test chạy trong Maven build. Đừng dùng `completed` của Failsafe làm “tổng unit + integration tests”.

## 18. Multi-module Maven: mỗi module có báo cáo riêng

Một Maven reactor có thể như sau:

~~~text
parent/
├── pom.xml
├── common/
│   ├── pom.xml
│   └── target/surefire-reports/
└── service/
    ├── pom.xml
    └── target/
        ├── surefire-reports/
        └── failsafe-reports/
~~~

Có thể `common` chỉ có unit tests, trong khi `service` có cả unit và IT. Khi chạy `mvn clean verify` từ parent, reports nằm ở từng module theo `project.build.directory`.

### Quy tắc tổng hợp đúng

1. Ghi **module artifactId/path** cho mỗi report.
2. Chỉ lấy kết quả của lần build/commit hiện tại.
3. Tách **plugin type** Surefire/Failsafe.
4. Tránh cộng một báo cáo aggregate cùng các báo cáo gốc của module.
5. Đọc fail message và testcase identity theo module.
6. Nếu một module fail, Maven reactor có thể ngừng các module phụ thuộc hoặc các module chưa được thực thi; “không có report” của module đó phải được ghi là **NOT RUN/UNKNOWN**, không phải PASS.

Một bảng CI hữu ích:

| Module | Unit tests | Unit result | IT tests | IT result | Ghi chú |
| --- | ---: | --- | ---: | --- | --- |
| `common` | 12 | PASS | 0 | NOT CONFIGURED | Module thư viện không có IT. |
| `service` | 8 | PASS | 4 | FAIL | `ReceiptGateIT` thất bại. |
| `web` | — | NOT RUN | — | NOT RUN | Bị bỏ qua do reactor dừng trước. |

Số liệu ở bảng trên **chỉ là tình huống minh họa**, không thuộc project thực hành. Không suy luận “0 tests” là thành công trừ khi module đó được thiết kế không có bộ test ấy.

### Dùng `-pl` và `-am` đúng mục đích

Có thể chạy module chọn lọc:

~~~bash
mvn -pl service -am verify
~~~

Lệnh minh họa này yêu cầu reactor xây module `service` và các module phụ thuộc phù hợp (nếu tồn tại trong project). Khi đó reports của các module được build trong lượt này có thể khác lượt chạy toàn reactor. Ghi rõ phạm vi khi so số test giữa hai job CI.

## 19. CI: ghép exit status và JUnit XML reports

Một quy trình CI tin cậy nên ghi nhận:

- **Exit status** của `mvn clean verify`: quyết định build gate cuối cùng.
- **Surefire reports**: những unit tests chạy, pass/fail/error/skip.
- **Failsafe reports**: những IT chạy, pass/fail/error/skip.
- **Failsafe summary**: bằng chứng Failsafe ghi tổng kết để verify.
- **Build ID, commit SHA, module, plugin versions, JDK version**: ngữ cảnh giúp tái hiện.
- **Artifacts logs** khi fork JVM crash hoặc hạ tầng lỗi.
- **Không có reports**: trạng thái riêng cần phân tích, không tự quy thành 0 failures.

### Upload reports ngay cả khi Maven fail

Trong một hệ thống CI, test reports nên được **lưu như artifacts kể cả khi job thất bại**, miễn không làm lộ dữ liệu nhạy cảm. Ví dụ workflow GitHub Actions có thể dùng điều kiện `if: always()` cho bước upload artifact:

~~~yaml
- name: Build and verify
  run: mvn --batch-mode clean verify

- name: Upload test reports
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: maven-test-reports
    path: |
      **/target/surefire-reports/
      **/target/failsafe-reports/
    if-no-files-found: warn
~~~

Đây là **mảnh YAML workflow minh họa**; cần đặt trong một job đúng cấu trúc (checkout, setup JDK/Maven, permissions). `if-no-files-found: warn` giúp quan sát tình huống không có report, nhưng nếu dự án có chính sách bắt buộc IT, CI nên có bước gate riêng kiểm tra bộ IT đã thật sự chạy.

### Bảo mật khi lưu report

JUnit XML có thể chứa:

- JVM system properties và environment-related fields.
- `system-out`, `system-err` với request/response bodies.
- Stack trace chứa hostname/URL nội bộ hoặc đường dẫn cá nhân.
- Test data và thông tin tài khoản giả lập nhưng vẫn có thể nhạy cảm.

Không đưa mật khẩu, token hoặc dữ liệu người dùng thật vào stdout của test. Kiểm soát quyền truy cập artifact CI và thời gian lưu reports.

## 20. Khi một IT thất bại, nên điều tra theo thứ tự nào?

Một quy trình có hệ thống:

1. **Xác nhận Maven chạy tới goal nào.** Nếu dừng ở Surefire test phase, đừng tìm lỗi trong Failsafe.
2. **Mở đúng module và thư mục `target/failsafe-reports`.**
3. **Đọc `failsafe-summary.xml`** để biết lỗi đã được Failsafe tổng hợp thế nào.
4. **Liệt kê `TEST-*.xml`**, tìm suite có `failures>0` hoặc `errors>0`.
5. **Xác định testcase** bằng `classname`/`name` và mở `*.txt` tương ứng.
6. **Đọc stack trace**: assertion mismatch, IOException, connection refused, timeout, DB constraint, server error hay crash JVM?
7. **Xem log setup/cleanup**, đặc biệt `pre-integration-test` và `post-integration-test`.
8. **Kiểm tra dependency của môi trường**: DB/container/service có sẵn, port có trùng, dữ liệu test có được reset, timezone/locale/JDK có khác CI?
9. **Chạy lại có mục tiêu**: một IT class với cấu hình tương đương, sau đó chạy toàn bộ `mvn clean verify` để tránh lỗi phụ thuộc thứ tự.
10. **Ghi kết luận theo hai nhóm**: Unit PASS/FAIL và IT PASS/FAIL/NOT RUN, kèm build status.

### Chạy một integration test có chủ đích

Với Failsafe 3.5.4, có thể chọn một IT bằng:

~~~bash
mvn -Dit.test=ReceiptFlowIT verify
~~~

Lệnh này là **bài thực hành chọn lọc**, phù hợp sau khi đã build/có class test và plugin configuration; Maven vẫn chạy các phase khác của lifecycle đến `verify` theo POM. User property `it.test` thường dùng để chọn test của Failsafe, khác với `-Dtest` của Surefire. Khi cần đảm bảo không bị nhầm hoặc có nhiều modules, đọc tài liệu version/plugin và xác nhận report mới tạo.

Nếu muốn chạy một unit test riêng:

~~~bash
mvn -Dtest=PriceCalculatorTest test
~~~

Lệnh này chạy phase `test` với Surefire, không xác minh IT. **Không dùng kết quả của một test riêng lẻ làm thay thế toàn bộ suites.**

## 21. Những lỗi thường gặp khi đọc và đối chiếu báo cáo

| Hiện tượng | Giải thích có thể | Cách xử lý |
| --- | --- | --- |
| `mvn test` thành công, không có `failsafe-reports`. | Chưa đến phase `integration-test`. | Chạy `mvn clean verify` để kiểm tra IT. |
| `BUILD FAILURE` nhưng Surefire reports đều PASS. | IT fail ở Failsafe, hoặc lỗi plugin/packaging/phase khác. | Đọc Failsafe reports, summary và Maven goal cuối. |
| `failsafe-summary.xml` có failure nhưng report XML một class đang xem PASS. | Failure thuộc class IT khác. | Liệt kê **toàn bộ** `TEST-*.xml` trong đúng module. |
| Không có report Failsafe sau `verify`. | Failsafe chưa bind, IT không discover, bị skip, build dừng sớm hoặc path đổi. | Xem effective POM, `failIfNoTests`, phase logs. |
| Unit test failure khiến không có IT report. | Maven dừng ở Surefire trước IT. | Sửa unit failure, chạy lại toàn lifecycle. |
| Số report files ít hơn số test methods. | Mỗi report file thường đại diện một test class/suite. | Cộng `tests` trong XML, không đếm file như đếm method. |
| Một test xuất hiện ở cả hai nhóm. | Includes/excludes bị cấu hình chồng lấn. | Kiểm tra naming và patterns của hai plugin. |
| XML counts khác text counts. | Retry/flaky policy, plugin provider, report files cũ hoặc XML transformations. | Kiểm tra schema, version, run ID và rerun config. |
| IT failure nhưng job CI vẫn đánh dấu PASS. | Chỉ chạy `integration-test` hoặc bỏ qua `verify`, hoặc ignore failure. | Dùng `mvn verify`, kiểm tra exit code và policy. |
| CI báo 0 IT nhưng success. | Không có tests hoặc skip, `failIfNoTests` chưa bật. | Đặt guard cho bộ IT được kỳ vọng, kiểm tra report count. |
| Test error do `ConnectException`. | Service/container chưa sẵn sàng hoặc port sai. | Điều tra setup, readiness và cleanup; không vội sửa assertion. |
| Test flaky chỉ khi chạy song song. | Chia sẻ file/port/DB hoặc state giữa forks/threads. | Cô lập resources, cấu hình fork/parallel phù hợp. |
| Report được upload nhưng có secret. | Test log/properties ghi thông tin nhạy cảm. | Mask dữ liệu, giảm log và kiểm soát artifact access. |
| `mvn integration-test` đã chạy mà server vẫn còn. | Chưa chạy `post-integration-test`/verify. | Dùng `mvn verify` và kiểm tra cleanup goal. |
| Test bị skip nhưng dashboard hiển thị màu xanh. | Success của build không nhất thiết đồng nghĩa coverage đủ. | Kiểm tra `tests/skipped` và policy bắt buộc. |

## 22. Checklist trước khi báo kết quả kiểm thử

- [ ] Đang xem đúng **module/POM**, build ID/commit và lượt chạy hiện tại.
- [ ] Có biết lệnh cuối là `mvn test`, `mvn integration-test` hay `mvn verify`.
- [ ] Surefire và Failsafe được cấu hình/pin version nhất quán, nếu chạy cả hai.
- [ ] Unit tests được discover đúng naming convention hoặc includes.
- [ ] IT classes được discover đúng naming convention hoặc includes.
- [ ] Có số tests thực thi kỳ vọng, không phải chỉ nhìn `0 failures`.
- [ ] Đã đọc tất cả report XML của mỗi nhóm, không chỉ một file PASS.
- [ ] `failures` và `errors` được phân biệt; skipped không bị báo là passed.
- [ ] Đã xét reruns/flaky nếu plugin/provider có bật.
- [ ] Failsafe `verify` thực sự được thực thi khi cần integration-test gate.
- [ ] `failsafe-summary.xml` tồn tại và phù hợp với trạng thái IT trong plugin version sử dụng.
- [ ] Nếu báo cáo thiếu, ghi `NOT RUN/UNKNOWN` hoặc nguyên nhân đã xác minh, không tự suy ra PASS.
- [ ] Với multi-module, không cộng report aggregate và module reports hai lần.
- [ ] Console logs và report artifacts đã được xử lý thông tin nhạy cảm.
- [ ] CI giữ báo cáo cả khi build FAIL để có chứng cứ chẩn đoán.

**Mẫu kết luận ngắn và đủ ngữ cảnh:**

~~~text
Module: failsafe-reports-demo
Command: mvn clean verify
Unit/Surefire: 3 tests, 0 failures, 0 errors, 0 skipped -> PASS
Integration/Failsafe: 3 tests, 0 failures, 0 errors, 0 skipped -> PASS
Failsafe verify: executed -> PASS
Maven build: BUILD SUCCESS
~~~

Đây là **kết luận kỳ vọng của demo**, không phải báo cáo được đọc từ một môi trường chưa chạy thực tế.

## 23. Bài tập thực hành

### Bài A — Đọc và phân loại

Cho hai thư mục:

~~~text
surefire-reports/
  TEST-demo.PriceCalculatorTest.xml  (tests=2, failures=0, errors=0, skipped=0)
  TEST-demo.ReceiptIdsTest.xml        (tests=1, failures=0, errors=0, skipped=0)

failsafe-reports/
  TEST-demo.ReceiptFlowIT.xml        (tests=2, failures=0, errors=0, skipped=0)
  TEST-demo.ReceiptGateIT.xml        (tests=1, failures=1, errors=0, skipped=0)
  failsafe-summary.xml
~~~

Câu hỏi:

1. Có bao nhiêu unit test methods? Bao nhiêu IT methods?
2. Nhóm nào PASS, nhóm nào FAIL?
3. Có thể kết luận Maven build cuối cùng PASS hay không nếu `failsafe:verify` chưa chạy?
4. Cần mở file nào để biết testcase IT thất bại và stack trace?
5. Nếu xóa file IT report nhưng giữ summary thì có còn đủ thông tin chẩn đoán không?
6. Nếu một suite có `skipped=2`, tại sao không nên báo cả hai là passed?

**Đáp án:** Unit có 3 methods PASS; IT có 3 methods, một assertion failure. Chưa thể báo integration-test gate hoàn tất khi chưa xác minh `failsafe:verify`; mở `TEST-demo.ReceiptGateIT.xml` và `demo.ReceiptGateIT.txt`. Summary giúp goal verify nhưng không thay được testcase-level stack trace.

### Bài B — Tự chạy Java 17

1. Tạo đầy đủ POM và tám file Java ở các mục 8–10.
2. Chạy `mvn clean test`. Ghi lại vì sao chưa có Failsafe report sau clean build.
3. Chạy `mvn clean verify`. Đọc hai thư mục reports, cộng riêng unit=3 và IT=3.
4. Mở `TEST-demo.ReceiptFlowIT.xml`, chỉ ra hai phần tử `testcase`.
5. Mở `failsafe-summary.xml` và đối chiếu số IT với test XML.
6. Chạy script `compare_reports.py` nếu có Python 3; đối chiếu output với manual counts.
7. Chạy `mvn -Ddemo.failIT=true clean verify`; kiểm tra unit reports vẫn PASS nhưng IT có failure.
8. Xác định Maven fail tại goal nào và giải thích vì sao Failsafe không dừng ngay ở integration-test.
9. Chạy lại `mvn clean verify` để đưa report về trạng thái PASS.
10. Lập một bảng CI ngắn có trạng thái Unit/IT/Build; không trộn dữ liệu của ba lượt chạy.

### Bài C — Giải thích tình huống production

CI chạy `mvn integration-test`, web service được khởi động ở `pre-integration-test` và tắt ở `post-integration-test`. Một IT fail, nhưng pipeline ghi nhận exit status không đúng kỳ vọng và process service còn chạy.

Hãy trả lời:

1. Vì sao chỉ dừng ở phase `integration-test` không đủ?
2. Failsafe `verify` dùng file nào để đánh giá kết quả?
3. Cần thay lệnh CI thành gì?
4. Nên lưu báo cáo nào khi build fail?
5. Nếu suite IT không được phát hiện do đổi tên từ `CheckoutIT` sang `CheckoutIntegrationTest`, bạn cần kiểm tra gì?
6. Vì sao “0 failures” không đủ nếu “0 tests”?

### Câu hỏi tự đánh giá

- `surefire-reports` và `failsafe-reports` mặc định phục vụ nhóm test nào?
- Vì sao Failsafe có hai goals `integration-test` và `verify`?
- `failsafe-summary.xml` có thay được từng `TEST-*.xml` không?
- Một file `TEST-*.xml` có tương đương một test method không?
- Assertion failure và unexpected error khác nhau thế nào trên report?
- `skipped=1` có thể được cộng vào passed không?
- Khi unit test fail trước IT phase, không có failsafe report nghĩa là gì?
- Trong multi-module project, vì sao không chỉ đọc `parent/target`?
- XML chứa `<flakyFailure>` cần được đọc theo chính sách nào?
- Vì sao clean build và build ID quan trọng khi so báo cáo?
- Một job CI có nên giữ test reports khi Maven exit nonzero?
- Câu lệnh nào bạn dùng khi muốn chắc chắn chạy cả cleanup và Failsafe verify?

## 24. Tổng kết

**Đọc report Maven đúng phải trả lời đồng thời ba câu hỏi: nhóm nào chạy, testcase nào đạt/không đạt, và goal/lifecycle đã kết thúc hợp lệ hay chưa.**

- Surefire thường chạy **unit tests** tại phase `test` và ghi `target/surefire-reports`.
- Failsafe chạy **integration tests** tại phase `integration-test`, ghi `target/failsafe-reports` và `failsafe-summary.xml`.
- Goal `failsafe:verify` đánh giá tổng kết IT để quyết định build failure, cho phép cleanup ở `post-integration-test` chạy trước khi báo lỗi test.
- File `*.txt` phục vụ đọc nhanh, `TEST-*.xml` phục vụ testcase-level/CI parsing, `failsafe-summary.xml` phục vụ tổng kết Failsafe.
- Tổng test count phải phân biệt `failures`, `errors`, `skipped`, flaky reruns, thiếu reports và các modules chưa chạy.
- Một lượt `mvn clean verify` có định danh rõ giúp so sánh báo cáo mới; không thay thế nó bằng `mvn integration-test` khi cần full lifecycle.
- **Unit PASS không chứng minh IT PASS**, và **không có IT report không có nghĩa IT PASS**.

Khi thiết kế pipeline, lưu cả Surefire/Failsafe reports, chốt plugin versions, xác minh số test thực chạy, giữ exit status của Maven và phân loại nguyên nhân lỗi theo từng test class/phase. Cách này biến một dòng `BUILD FAILURE` thành bằng chứng có cấu trúc và quyết định xử lý rõ ràng.

## Tài liệu chính thức

- Apache Maven — Maven Failsafe Plugin: https://maven.apache.org/surefire/maven-failsafe-plugin/
- Apache Maven — Maven Surefire Plugin: https://maven.apache.org/surefire/maven-surefire-plugin/
- Maven Failsafe Plugin — Usage: https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html
- Maven Failsafe Plugin — `failsafe:integration-test`: https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html
- Maven Failsafe Plugin — `failsafe:verify`: https://maven.apache.org/surefire/maven-failsafe-plugin/verify-mojo.html
- Maven Failsafe Plugin — Inclusions and Exclusions: https://maven.apache.org/surefire/maven-failsafe-plugin/examples/inclusion-exclusion.html
- Maven Surefire Plugin — Inclusions and Exclusions: https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion.html
- Apache Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/

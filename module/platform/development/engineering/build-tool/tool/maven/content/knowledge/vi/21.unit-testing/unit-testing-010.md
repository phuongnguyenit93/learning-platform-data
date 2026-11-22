# Kiểm thử lỗi, kiểm thử không ổn định và chính sách thất bại trong Maven

## 1. Mục tiêu: test đỏ phải có ý nghĩa

Trong một dự án Java sử dụng Maven, `mvn test` có thể kết thúc với `BUILD FAILURE` vì unit test phát hiện kết quả sai, vì test gặp ngoại lệ, vì JVM fork bị lỗi hoặc vì công cụ kiểm thử không chạy được. Ngược lại, một lần `BUILD SUCCESS` **không bảo đảm** mọi test đã được chạy: test có thể bị skip, không được phát hiện, hoặc một test lỗi ở lần chạy đầu đã PASS sau khi Surefire retry.

Ba câu hỏi cần phân biệt:

1. **Kiểm thử lỗi (failing/error tests)**: một phép kiểm tra thất bại theo cách có thể tái hiện, hoặc mã đang chạy ném ngoại lệ không mong đợi.
2. **Kiểm thử không ổn định (flaky tests)**: cùng test trên cùng phiên bản code và điều kiện được kỳ vọng tương đương đôi khi PASS, đôi khi FAIL; thường do phụ thuộc thời gian, thứ tự, thread, dữ liệu chia sẻ, network, môi trường hoặc thiếu isolation.
3. **Chính sách thất bại (failure policy)**: khi nào Maven/CI phải dừng với trạng thái lỗi, khi nào cho retry, khi nào chấp nhận tạm thời flake và làm sao ngăn retry che regression thật.

Mục tiêu không phải làm cho mọi pipeline xanh bằng mọi giá. Mục tiêu là biến **kết quả kiểm thử thành tín hiệu đáng tin**: lỗi thật làm build thất bại; flake được ghi nhận và xử lý; test bị bỏ qua không bị hiểu nhầm thành test đạt.

Bài này tập trung vào **unit tests trong Maven Surefire Plugin**, sử dụng JUnit Jupiter (JUnit 5) trên **Java 17**. Integration tests qua Maven Failsafe Plugin có một số khác biệt ở lifecycle và tham số; sẽ phân biệt trong phần sau.

## 2. Luồng kiểm thử đơn vị trong default lifecycle

Với project `jar` thông thường:

~~~text
validate
   |
process-resources
   |
compile
   |
process-test-resources
   |
test-compile
   |
test
   └── maven-surefire-plugin:surefire:test
           ├── tìm test classes
           ├── JUnit Platform/Jupiter chạy test
           ├── ghi reports (*.txt, TEST-*.xml)
           └── trả kết quả PASS/FAIL cho Maven
   |
package
   |
verify
   |
install
   |
deploy
~~~

Lệnh:

~~~bash
mvn -B -ntp clean test
~~~

gọi clean lifecycle, rồi default lifecycle đến `test`. Nếu Surefire báo test failures/errors và cấu hình không bỏ qua lỗi, Maven dừng với `BUILD FAILURE` và process exit code khác 0. Các phase phía sau như `package` sẽ không tiếp tục trong đường chạy thông thường.

Trong `mvn clean verify`, Surefire vẫn chạy ở `test`; các goal khác có thể được bind ở các phase sau. Maven **không tự động xử lý** flaky test bằng cách chạy lại, trừ khi đã cấu hình hoặc chỉ định tính năng retry của công cụ.

## 3. Phân biệt failure, error, skip và flake

| Trạng thái | Nghĩa trong thực hành | Ví dụ |
| --- | --- | --- |
| **PASS** | Test chạy xong và các assertions/điều kiện đều đạt | `assertEquals(4, add(2, 2))` |
| **Failure** | Một assertion hoặc điều kiện kỳ vọng bị vi phạm | `assertEquals(5, add(2, 2))` |
| **Error** | Test/setup/runtime gặp ngoại lệ không mong đợi hoặc lỗi thực thi | `IllegalStateException` từ code test |
| **Skipped/disabled** | Test được bỏ qua theo annotation/filter/điều kiện | `@Disabled` hoặc `@EnabledIfSystemProperty` không khớp |
| **Flake** | Một test fail trong lần chạy đầu nhưng PASS ở lần rerun cùng đợt | Lần đầu thiếu marker, lần sau có marker |
| **Not discovered** | Không có test nào được test runner phát hiện phù hợp | Đặt tên class không khớp pattern Surefire |
| **Infrastructure failure** | Tool/plugin, JVM fork, dependency hoặc môi trường không thể chạy test bình thường | Fork JVM crash, không resolve plugin, hết bộ nhớ |

**Lưu ý kỹ thuật:** JUnit Jupiter nhìn chung coi assertion failure và exception không mong đợi đều là những tình huống test thất bại. Trong báo cáo Surefire/JUnit provider, `AssertionError` thường được thể hiện như **Failures**, còn những ngoại lệ runtime không mong đợi thường thành **Errors**. Việc phân loại chi tiết phụ thuộc provider/report, nên cần đọc report XML và stack trace chứ không gán mọi ngoại lệ vào cùng một nhóm.

Đặc biệt, `assertThrows(IllegalArgumentException.class, ...)` **PASS** nếu code ném đúng loại exception. Kiểm thử đường lỗi của ứng dụng không phải là một **test thất bại**; nó thường là một test **đạt** vì phát hiện hành vi lỗi đã được xử lý đúng hợp đồng.

## 4. Một ngoại lệ được kỳ vọng không làm test đỏ

Giả sử một phép chia phải từ chối mẫu số bằng 0:

~~~java
public static int divide(int left, int right) {
    if (right == 0) {
        throw new IllegalArgumentException("division by zero");
    }
    return left / right;
}
~~~

Test đúng nên xác nhận exception:

~~~java
IllegalArgumentException error =
        assertThrows(IllegalArgumentException.class,
                () -> Calculator.divide(10, 0));
assertEquals("division by zero", error.getMessage());
~~~

Trong trường hợp này, test **PASS**, vì code được thiết kế để ném exception khi input không hợp lệ.

Ngược lại:

~~~java
Calculator.divide(10, 0);
~~~

nếu gọi trong test mà không bắt/không assertion rằng exception được kỳ vọng, test sẽ thất bại. Cùng hành vi ứng dụng có thể được phân loại khác nhau tùy **hợp đồng kiểm thử**.

`assertThrows` chấp nhận exception thuộc lớp được chỉ định **hoặc subclass**. `assertThrowsExactly` yêu cầu **đúng** lớp exception. Chọn cách kiểm tra phù hợp với public contract, tránh ràng buộc quá chặt với implementation detail.

## 5. Surefire và chính sách mặc định

Maven Surefire Plugin thường được bind vào phase `test` cho packaging Java tương ứng. Những tham số đáng chú ý của Surefire 3.6.1:

| Tham số | Giá trị mặc định | Ý nghĩa |
| --- | --- | --- |
| `testFailureIgnore` | `false` | Test fail/error khiến goal không thành công, build thường FAIL |
| `rerunFailingTestsCount` | `0` | Không chạy lại test thất bại |
| `failOnFlakeCount` | `0` | Không đặt giới hạn số flake; chỉ khi bật retry mới phát sinh flake được ghi nhận |
| `failIfNoTests` | `false` | Mặc định không fail chỉ vì không phát hiện test |
| `failIfNoSpecifiedTests` | `true` | Khi chọn test cụ thể bằng `-Dtest=...` mà không match, mặc định fail |
| `skipTests` | `false` | Không bỏ qua test execution |
| `skipAfterFailureCount` | `0` | Không yêu cầu dừng sớm sau N failures/errors |

**Chính sách đề xuất cho CI:** phải fail khi test thực sự lỗi, fail khi dự án dự kiến có test nhưng không phát hiện test, và không âm thầm bỏ qua test. Retry flake nếu tổ chức lựa chọn thì phải lưu report và có giới hạn rõ ràng.

Tham số `failOnFlakeCount` có quy ước đặc biệt: `0` nghĩa là **không đặt ngưỡng**, **không phải “không cho phép flake”**. Ví dụ muốn build fail ngay khi có flake được ghi nhận, đặt `failOnFlakeCount=1` trên plugin hỗ trợ.

## 6. Dự án Java 17 runnable: test đúng, test lỗi và test flake

Ta tạo một project Maven **mặc định chạy xanh**, nhưng có thể bật riêng hai nhóm test có lỗi **có chủ ý** qua JVM system properties. Cách này giúp người học thực hành chính sách thất bại mà không làm mọi lần `mvn clean verify` mặc định đều đỏ.

Cấu trúc:

~~~text
test-policy-lab/
├── pom.xml
└── src/
    ├── main/java/demo/testing/Calculator.java
    └── test/java/demo/testing/
        ├── CalculatorTest.java
        ├── FailureGalleryTest.java
        └── FlakyDemoTest.java
~~~

Yêu cầu Java 17+, Maven phù hợp với plugins đã ghim và quyền tải Maven dependencies từ repository hợp lệ. Demo flake cố ý lưu một **marker dưới `target`** và không được đưa vào CI production.

### 6.1. `pom.xml` hoàn chỉnh

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo.testing</groupId>
    <artifactId>test-policy-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <demo.failure>false</demo.failure>
        <demo.flake>false</demo.flake>
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
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                    <systemPropertyVariables>
                        <demo.failure>${demo.failure}</demo.failure>
                        <demo.flake>${demo.flake}</demo.flake>
                    </systemPropertyVariables>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Giải thích:

- `junit-jupiter` cung cấp annotations và assertions của JUnit Jupiter, chỉ ở scope `test`.
- Surefire 3.6.1 là phiên bản hiện hành được dùng để giải thích các tính năng rerun/flaky trong bài; **phiên bản được cố định cho ví dụ**, không phải lời hứa sẽ luôn mới nhất.
- `failIfNoTests=true` giúp tránh build “xanh nhưng không có test được phát hiện” đối với module thực sự được thiết kế có unit tests.
- Hai thuộc tính `demo.failure` và `demo.flake` mặc định `false`, được truyền vào **forked test JVM** qua `systemPropertyVariables`. CLI có thể override chúng bằng `-Ddemo.failure=true` hoặc `-Ddemo.flake=true`.
- Không ghi cố định `rerunFailingTestsCount`, `failOnFlakeCount` hoặc `testFailureIgnore` trong POM. Khi đó có thể dùng đúng user properties trên command line để minh họa các chính sách mà không bị XML configuration cố định ghi đè.
- Demo không dùng Spring hoặc database, nên có thể phân biệt lỗi logic/test với lỗi hạ tầng.

### 6.2. `src/main/java/demo/testing/Calculator.java`

~~~java
package demo.testing;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int a, int b) {
        return Math.addExact(a, b);
    }

    public static int divide(int numerator, int denominator) {
        if (denominator == 0) {
            throw new IllegalArgumentException("division by zero");
        }
        return numerator / denominator;
    }

    public static void main(String[] args) {
        System.out.println("2 + 2 = " + add(2, 2));
    }
}
~~~

Class chạy độc lập bằng Java 17 sau khi Maven compile. Dùng `Math.addExact` để phép cộng số nguyên phát hiện overflow thay vì âm thầm wraparound. Không có dependency runtime ngoài JDK.

### 6.3. `src/test/java/demo/testing/CalculatorTest.java`

~~~java
package demo.testing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(4, Calculator.add(2, 2));
    }

    @Test
    void dividesNormally() {
        assertEquals(2, Calculator.divide(8, 4));
    }

    @Test
    void rejectsZeroDenominator() {
        IllegalArgumentException error =
                assertThrows(IllegalArgumentException.class,
                        () -> Calculator.divide(8, 0));
        assertEquals("division by zero", error.getMessage());
    }
}
~~~

Đây là **ba test đúng**:

- `addsTwoNumbers` và `dividesNormally` kiểm tra normal path.
- `rejectsZeroDenominator` kiểm tra **error path của ứng dụng**, nhưng test **PASS** vì đúng exception được assert.

Không nhầm “test một điều kiện lỗi” với “test run bị lỗi”.

### 6.4. `src/test/java/demo/testing/FailureGalleryTest.java`

~~~java
package demo.testing;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;

@EnabledIfSystemProperty(named = "demo.failure", matches = "true")
class FailureGalleryTest {
    @Test
    void intentionallyFailsAssertion() {
        assertEquals(5, Calculator.add(2, 2));
    }

    @Test
    void intentionallyThrowsUnexpectedException() {
        throw new IllegalStateException("demo unexpected exception");
    }
}
~~~

Hai test được bật **chỉ khi JVM property `demo.failure=true`**. Ở chế độ mặc định, JUnit Jupiter **discover nhưng disable** class vì property là `false`. Đừng đưa các test cố ý sai này vào source production; chúng tồn tại để học cách Surefire báo cáo failure và error.

Khi bật, test thứ nhất thất bại do `expected: <5> but was: <4>` (format có thể thay đổi theo JUnit). Test thứ hai gặp `IllegalStateException` chưa được kỳ vọng. Surefire thường ghi lần lượt vào phần Failures và Errors trong report, kèm stack traces; build FAIL khi không bật ignore.

### 6.5. `src/test/java/demo/testing/FlakyDemoTest.java`

~~~java
package demo.testing;

import static org.junit.jupiter.api.Assertions.fail;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;

@EnabledIfSystemProperty(named = "demo.flake", matches = "true")
class FlakyDemoTest {
    @Test
    void failsOnceThenPasses() throws IOException {
        Path marker = Path.of("target", "flaky-demo.marker");
        Files.createDirectories(marker.getParent());

        if (Files.notExists(marker)) {
            Files.writeString(marker, "first-attempt-was-here");
            fail("intentional first-attempt failure");
        }
    }
}
~~~

Đây là một **bài biểu diễn có chủ đích về test phụ thuộc state**:

1. `clean` xóa thư mục `target`, gồm marker nếu có.
2. Lần chạy đầu của `failsOnceThenPasses` không tìm thấy marker, tạo marker rồi `fail(...)`.
3. Khi Surefire **rerun cùng test mà không clean giữa các lần**, marker tồn tại và test PASS.
4. Surefire có thể ghi nhận một **flake** thay vì một failure cuối cùng, tùy cấu hình rerun và báo cáo.

**Không được dùng kỹ thuật marker để “sửa” flaky test thật.** Đây là anti-pattern được cố tình tạo để quan sát retry. Test tốt phải độc lập với các lần chạy trước; marker còn sót khi gọi `mvn test` không `clean` có thể khiến demo PASS ngay ở lần đầu. Khi đánh giá behavior, phải **bắt đầu bằng `clean`** và không chạy song song các lệnh cùng ghi vào `target`.

## 7. Chạy baseline: project xanh khi không bật test cố ý lỗi

Tại thư mục `test-policy-lab`:

~~~bash
mvn -version
mvn -B -ntp clean test
~~~

Kết quả kỳ vọng:

- Ba test trong `CalculatorTest` chạy và PASS.
- Hai test trong `FailureGalleryTest` bị JUnit disable vì `demo.failure=false`.
- Test trong `FlakyDemoTest` bị disable vì `demo.flake=false`.
- Maven báo `BUILD SUCCESS`.

Phần thống kê có thể hiển thị `Skipped` cho các test có annotation điều kiện. Số cách đếm container/test bị skip có thể phụ thuộc JUnit Platform và Surefire provider; không nên chốt một con số thay cho report thực.

Sau đó chạy Java main:

~~~bash
java -cp target/classes demo.testing.Calculator
~~~

**Stdout chính xác:**

~~~text
2 + 2 = 4
~~~

Lệnh Java này là bước riêng; `mvn test` không tự gọi `Calculator.main()`. Test reports nằm dưới `target/surefire-reports`, thông thường có các file `TEST-*.xml` và `*.txt`.

## 8. Bật assertion failure và unexpected exception

Bật riêng test cố ý sai:

~~~bash
mvn -B -ntp clean test -Ddemo.failure=true
~~~

Kỳ vọng:

1. `CalculatorTest` vẫn PASS.
2. `FailureGalleryTest.intentionallyFailsAssertion` báo failed assertion.
3. `FailureGalleryTest.intentionallyThrowsUnexpectedException` báo unexpected exception.
4. Không bật flake test vì `demo.flake=false`.
5. Surefire trả lỗi, Maven kết thúc bằng `BUILD FAILURE` và process exit code khác 0.

Thông điệp thường chứa tên class/method:

~~~text
FailureGalleryTest.intentionallyFailsAssertion
expected: <5> but was: <4>

FailureGalleryTest.intentionallyThrowsUnexpectedException
java.lang.IllegalStateException: demo unexpected exception

BUILD FAILURE
~~~

Đây là **trích đoạn minh họa**, không phải transcript thật. Số dòng, thứ tự và format thực tế phụ thuộc JUnit/Surefire. Không cam kết rằng failures và errors lúc nào cũng in theo thứ tự source.

Để chỉ chạy class này (đã có POM và source đúng):

~~~bash
mvn -B -ntp test -Dtest=FailureGalleryTest -Ddemo.failure=true
~~~

Nếu mục đích là tái hiện từ trạng thái sạch thì thêm `clean`:

~~~bash
mvn -B -ntp clean test -Dtest=FailureGalleryTest -Ddemo.failure=true
~~~

**Chú ý:** `-Dtest=FailureGalleryTest` là chỉ thị chọn test class/method của Surefire, không phải khai báo Maven profile. Nó không làm một test đã bị `@EnabledIfSystemProperty` disable tự active; còn cần property `demo.failure=true`.

## 9. Báo cáo thực tế: tìm root cause ở đâu?

Trong mặc định Surefire:

~~~text
target/surefire-reports/
├── TEST-demo.testing.CalculatorTest.xml
├── demo.testing.CalculatorTest.txt
├── TEST-demo.testing.FailureGalleryTest.xml
└── demo.testing.FailureGalleryTest.txt
~~~

Danh sách chỉ minh họa những file thường gặp; khi test disable hoặc provider/plugin config khác, số file/tên file có thể thay đổi.

Trong JUnit XML report, một test thường có thông tin dưới các thẻ như:

~~~xml
<testsuite name="..." tests="..." errors="..." skipped="..." failures="...">
    <testcase name="intentionallyFailsAssertion" classname="...">
        <failure message="..." type="...">...</failure>
    </testcase>
    <testcase name="intentionallyThrowsUnexpectedException" classname="...">
        <error message="..." type="...">...</error>
    </testcase>
</testsuite>
~~~

Đây là **mẫu cấu trúc XML có placeholder dấu ba chấm để giải thích**, không phải output cần copy làm file chạy. Báo cáo có thể kèm `system-out`, `system-err`, thời gian và property.

Khi nhận incident:

- Đọc **lỗi đầu tiên** có ý nghĩa, không chỉ `BUILD FAILURE` ở cuối.
- Ghi class/method và stack trace, exception type, assert expected/actual.
- Xem test nào được **skip**, test nào thật sự chạy.
- Đối chiếu version JDK, Surefire, JUnit, module, active Maven profile và flags.
- Nếu có retry, phải giữ **cả thông tin lần fail lẫn lần rerun PASS**, tránh chỉ lưu kết quả cuối.

Đừng đăng nguyên full Surefire reports vào nơi công khai nếu chúng chứa nội dung kiểm thử, endpoint, token hoặc thông tin dữ liệu nhạy cảm.

## 10. Flaky tests: dấu hiệu, nguyên nhân và cách nhận biết

Một test được gọi là **flaky** khi kết quả không ổn định dưới những điều kiện được kỳ vọng tương đương; ví dụ cùng commit, dependency versions và test inputs mà lần đầu FAIL, chạy lại PASS. Đây là triệu chứng của vấn đề cần điều tra, không phải một loại test “ít quan trọng”.

Những nguyên nhân phổ biến:

| Nhóm | Ví dụ nguyên nhân | Biện pháp |
| --- | --- | --- |
| **Thời gian** | So sánh với `System.currentTimeMillis()`, test chờ bằng `Thread.sleep(100)` | Inject `Clock`, fake scheduler hoặc dùng điều kiện chờ có timeout hợp lý |
| **Random** | Random không cố định seed, sinh data khác nhau mỗi lần | Dùng seed có thể log và tái hiện; property-based testing lưu case |
| **Concurrency** | Race condition, deadlock, không chờ Future/task hoàn thành | Đồng bộ đúng, kiểm soát executor, tránh assertions ngoài thread đang được runner theo dõi |
| **Shared state** | Test A thay đổi static cache/test database mà test B dùng | Isolation theo test, setup/teardown, tránh phụ thuộc order |
| **External service** | HTTP/database/network rate limit, DNS, service khởi động chậm | Dùng mock/fake cho unit tests, integration tests riêng |
| **Environment** | Timezone, locale, OS, file separator, JDK version khác | Thiết lập/khôi phục môi trường có chủ đích, xử lý portable |
| **Filesystem** | File `target` còn từ build trước, temp file tên trùng | Sử dụng `@TempDir`, cleanup, tránh sharing path |
| **Resource limits** | CPU CI bị quá tải, RAM thấp, timeout quá gắt | Điều chỉnh workload và timeout có cơ sở, thu thập metrics |
| **Order-sensitive tests** | Test phụ thuộc test khác chạy trước | Tự setup state, randomize/repeat theo chính sách |
| **Uncaught background exceptions** | Async task fail nhưng test kết thúc trước | Chờ completion và propagate lỗi về thread test |

Một test có lỗi **cố định** không nhất thiết là flaky. Nếu luôn FAIL khi chạy cùng đầu vào, đó là regression hoặc assertion sai; cần sửa trực tiếp, không bắt đầu bằng retry.

### 10.1. Kỹ thuật điều tra

Một quy trình có hệ thống:

1. Lưu commit/hash, JDK, Surefire/JUnit versions, OS, container image và command line.
2. Chạy **test cụ thể** nhiều lần trong điều kiện đã kiểm soát; không lặp vô hạn.
3. So kết quả khi chạy **một mình** và khi chạy **cùng toàn bộ suite**.
4. So local với CI và so chạy tuần tự với parallel nếu có.
5. Thu thập seed, timezone, locale, fake server state, test order và thread dump khi kẹt.
6. Kiểm tra teardown của test trước có làm rò static state, file, port hay database row không.
7. Viết một regression test **deterministic** mô phỏng nguyên nhân, thay vì giữ lại phụ thuộc ngẫu nhiên.
8. Sau fix, chạy lại nhiều lần với điều kiện phù hợp và giám sát flake rate theo thời gian.

Nếu muốn đo flaky rate, cần định nghĩa cách đếm: **số test cases flaky trên tổng số test cases chạy**, hoặc **số runs có ít nhất một flake**, chứ không trộn hai đại lượng.

## 11. Rerun failing tests trong Surefire

Surefire hỗ trợ chạy lại các test thất bại bằng tham số:

~~~bash
mvn -B -ntp test -Dsurefire.rerunFailingTestsCount=2
~~~

Với `2`, mỗi test thất bại được thử **tối đa hai lần chạy lại** sau lần đầu, tức tổng cộng tối đa ba attempts cho test đó. Nếu PASS ngay, test không cần rerun.

Theo Surefire hiện hành, tính năng này hỗ trợ JUnit 4, JUnit Platform/JUnit Jupiter và TestNG trong những provider/version được nêu ở tài liệu. **Không dùng tài liệu Surefire 2.22.x rồi kết luận JUnit 5 không hỗ trợ rerun trên Surefire 3.6.x**: khả năng hỗ trợ thay đổi theo version.

### Khi retry thành công

Ví dụ một test FAIL ở lần đầu, PASS ở lần thứ hai:

~~~text
Run 1: FAIL
Run 2: PASS
Flakes: 1
~~~

Đây là mẫu ý nghĩa, không phải nguyên log Surefire. Với `rerunFailingTestsCount > 0` và `failOnFlakeCount=0` mặc định, một test đã hồi phục có thể khiến build **SUCCESS**, trong khi Surefire vẫn ghi nhận nó là **flake**.

### Khi retry hết lần mà vẫn lỗi

~~~text
Run 1: FAIL
Run 2: FAIL
Run 3: FAIL
BUILD FAILURE
~~~

Nếu `rerunFailingTestsCount=2` thì đó là tối đa ba lần. Đây là một **test đang fail**, dù nó đã được retry; không được báo “flaky đã qua” nếu test cuối vẫn lỗi.

### Cách Surefire báo cáo XML khi rerun

Khi test FAIL rồi PASS, XML có thể có các phần tử `<flakyFailure>` hoặc `<flakyError>` lưu thông tin các lần fail, và sau đó là kết quả PASS. Khi mọi attempts đều FAIL, report dùng `<failure>`/`<error>` cho lỗi chính và các phần tử `<rerunFailure>`/`<rerunError>` cho lần retry.

CI chỉ đọc một con số “failures=0” mà bỏ qua `flakyFailure` có thể **bỏ sót rủi ro flake**. Nếu bật retry, phải dùng parser/reporting hiểu định dạng Surefire tương ứng.

## 12. Thử nghiệm flake có kiểm soát

Để thử riêng `FlakyDemoTest`, dùng command line sau **từ trạng thái clean**:

~~~bash
mvn -B -ntp clean test -Dtest=FlakyDemoTest -Ddemo.flake=true -Dsurefire.rerunFailingTestsCount=1
~~~

Trong ví dụ:

1. `clean` xóa marker.
2. Lần đầu test FAIL và tạo `target/flaky-demo.marker`.
3. Surefire rerun test, marker đã tồn tại nên PASS.
4. Test được ghi nhận là **flaky**.
5. Vì `failOnFlakeCount` mặc định là `0`, build **có thể SUCCESS**, nhưng report vẫn có bằng chứng thất bại ở lần đầu.

Để xem dữ liệu flake, tìm report class:

~~~text
target/surefire-reports/TEST-demo.testing.FlakyDemoTest.xml
~~~

Phần XML liên quan có thể trông giống:

~~~xml
<testcase name="failsOnceThenPasses" classname="demo.testing.FlakyDemoTest">
    <flakyFailure message="intentional first-attempt failure" type="...">
        ...
    </flakyFailure>
</testcase>
~~~

Đây là **ví dụ minh họa cấu trúc**, không phải XML output chính xác tuyệt đối. Các element, stack traces và property được Surefire sinh dựa trên provider/version.

**Quan trọng:** Đây là một ví dụ *flaky được dựng có chủ ý*, sử dụng file marker; có thể PASS ngay nếu chạy lại mà không clean. Thực tế, điều đó càng chứng minh file state ngoài test là nguồn flakiness. Không giữ đoạn code này trong một unit test suite production.

## 13. Chính sách nghiêm: fail nếu phát hiện flake

Surefire 3.6.1 hỗ trợ `failOnFlakeCount` để làm build thất bại nếu số flake đạt ngưỡng dương được cấu hình.

Thử với test demo:

~~~bash
mvn -B -ntp clean test -Dtest=FlakyDemoTest -Ddemo.flake=true -Dsurefire.rerunFailingTestsCount=1 -Dsurefire.failOnFlakeCount=1
~~~

Kỳ vọng:

- Test đầu tiên FAIL.
- Rerun PASS.
- Surefire nhận diện **1 flake**.
- Vì ngưỡng đặt là `1`, build kết thúc **FAILURE** theo chính sách chống flake, dù lần cuối test đã PASS.

Phân biệt hai trạng thái:

| Rerun | Ngưỡng flake | Test sau retries | Build policy |
| --- | --- | --- | --- |
| Tắt rerun (0) | Bất kỳ | Lỗi ở attempt đầu | FAIL do test failure |
| 1 lần rerun | `0` | PASS lần sau, 1 flake | Có thể SUCCESS, flake được ghi nhận |
| 1 lần rerun | `1` | PASS lần sau, 1 flake | FAIL vì vượt/đạt ngưỡng flake |
| 1 lần rerun | `1` | FAIL cả hai lần | FAIL do test failure |

`failOnFlakeCount=0` **không phải** chính sách zero tolerance; nó vô hiệu hóa giới hạn flake. Muốn zero tolerance khi sử dụng rerun, cấu hình ngưỡng dương tối thiểu `1`. Tài liệu từng phiên bản dùng cách diễn đạt “reaches threshold” hoặc “more than” trong các trang khác nhau; trong bài thực hành này, chọn `1` để yêu cầu fail khi có flake đầu tiên theo tham số goal hiện hành.

**Không nên đặt retries cao vô hạn** để “làm xanh” pipeline. Mỗi rerun tốn thời gian, kéo dài phản hồi và che điều kiện race. Giới hạn số lần (ví dụ 1–2) và theo dõi flake rate khi đã quyết định sử dụng.

## 14. Chính sách bỏ qua thất bại: testFailureIgnore

Một cờ nguy hiểm nếu dùng sai:

~~~bash
mvn -B -ntp clean test -Ddemo.failure=true -Dmaven.test.failure.ignore=true
~~~

Nó yêu cầu Surefire **không làm build thất bại chỉ vì test failure/error** (theo phạm vi plugin/goal hỗ trợ). Trong demo, test vẫn có thể chạy, tạo báo cáo về failures/errors, nhưng Maven có thể kết thúc `BUILD SUCCESS` dù tests đỏ.

Đó là lý do tính năng này được tài liệu Surefire cảnh báo **không khuyến nghị** dùng thường xuyên.

Phân biệt hai việc:

- **Bỏ qua lỗi test**: test có thể được chạy và ghi nhận lỗi, nhưng Maven không chặn build.
- **Bỏ qua chạy test**: test không thực thi, nên không có bằng chứng kết quả mới.

Không bật `maven.test.failure.ignore=true` trên release pipeline chỉ vì cần deploy gấp mà không có một quality gate khác đã được review. Khi build xanh do ignore, phải báo rõ **tests FAILED** trong báo cáo; nếu không, người đọc dễ hiểu nhầm chất lượng artifact.

### Tình huống hợp lệ có điều kiện

Trong một pipeline chẩn đoán hoặc giai đoạn thu thập dữ liệu, có thể cho phép job gom report mặc dù test fail, nhưng **job xuất bản artifact** vẫn phải phụ thuộc vào một gate bắt buộc đánh giá kết quả. Tùy hệ thống CI, cách triển khai thường tốt hơn là để test step fail, nhưng cấu hình **artifact/report upload chạy kể cả khi thất bại**. Không nên biến việc xuất hiện report thành “build thành công”.

## 15. Không có test nào: failIfNoTests và test discovery

Một module có mã Java nhưng test đã đổi tên/di chuyển. Maven Surefire vẫn có thể cho build SUCCESS nếu không phát hiện test, bởi `failIfNoTests` mặc định `false`.

Trong project demo ta đặt:

~~~xml
<failIfNoTests>true</failIfNoTests>
~~~

để project **có nghĩa vụ có unit tests** fail khi thực sự không có test nào được tìm thấy theo logic provider.

Các naming conventions thường được Surefire phát hiện:

~~~text
Test*.java
*Test.java
*Tests.java
*TestCase.java
~~~

Đây là các patterns mặc định thông dụng của Surefire; provider và cấu hình includes/excludes có thể mở rộng thay đổi.

Ví dụ tên `CalculatorCheck.java` không nhất thiết được tìm thấy như test nếu không thay includes. Vì vậy không nên nghĩ `@Test` xuất hiện trong source thì Surefire chắc chắn chạy class đó trong mọi cấu hình.

### Phân biệt hai tham số

- `failIfNoTests`: quy tắc khi **không có test nào chạy/được phát hiện phù hợp** theo plugin.
- `failIfNoSpecifiedTests`: quy tắc khi đã yêu cầu test cụ thể bằng `-Dtest=...` nhưng không match; thường mặc định true.

Ví dụ gọi sai tên:

~~~bash
mvn -B -ntp test -Dtest=MissingCalculatorTest
~~~

thường làm Surefire báo lỗi vì không có test khớp pattern chỉ định.

**Trường hợp đặc biệt:** Có test được discover nhưng bị JUnit `@Disabled`/conditional annotation skip là chuyện **khác** với không có test được tìm thấy. `failIfNoTests` không nên được xem là biện pháp duy nhất chống suite mà mọi test đều bị skip; CI nên kiểm tra số lượng test **executed**, skipped và ngưỡng tối thiểu phù hợp.

Một multi-module parent có packaging `pom` và không có test không nên bị áp chính sách giống một module unit-test `jar` mà không xét phạm vi cấu hình.

## 16. skipTests, maven.test.skip và skipped by annotation

Ba cách bỏ qua khác nhau:

| Cách | Điều gì thường xảy ra? | Rủi ro |
| --- | --- | --- |
| `-DskipTests` | Surefire bỏ qua **thực thi test**, còn test source vẫn có thể được biên dịch | Không có kết quả test mới |
| `-Dmaven.test.skip=true` | Compiler Plugin và Surefire có thể bỏ qua cả **test compilation** và execution | Ẩn lỗi compile ở test code |
| `@Disabled` / `@EnabledIfSystemProperty` không khớp | JUnit discover nhưng skip những test cụ thể | Coverage suy giảm mà build vẫn xanh |
| `-Dtest=SomeTest` | Chỉ chọn một test/class pattern, không phải skip toàn bộ | Các test còn lại không chạy |

Lệnh ví dụ:

~~~bash
mvn -B -ntp clean package -DskipTests
mvn -B -ntp clean package -Dmaven.test.skip=true
~~~

Hai lệnh trên **không phải phép kiểm chứng thay cho `mvn clean verify`**. Nếu không có yêu cầu ngoại lệ rõ ràng, không dùng trên CI quality gate chính.

**Lưu ý version:** từ Failsafe 3.6.x, hành vi user property `skipTests` đã được tách rõ để tránh vô tình ảnh hưởng cả integration tests. Khi muốn skip integration tests, dùng `-DskipITs` nếu phiên bản Failsafe hỗ trợ; muốn skip nhiều loại test bằng `maven.test.skip` phải hiểu phạm vi. Đừng sao chép một cờ từ tài liệu plugin đời cũ rồi giả định nó có cùng hiệu lực trên mọi phiên bản.

## 17. Dừng sau N lỗi: skipAfterFailureCount

Khi một suite lớn liên tiếp fail do cùng sự cố, Surefire có tham số:

~~~bash
mvn -B -ntp test -Dsurefire.skipAfterFailureCount=1
~~~

Với `1`, plugin yêu cầu không tiếp tục chạy những test còn lại sau khi đã nhận một failure/error, trong giới hạn hỗ trợ của provider và fork/parallel model.

**Không xem đây là đảm bảo “chỉ đúng một test được chạy sau lỗi đầu”**. Trong parallel/forked execution có race conditions; test đã được schedule có thể vẫn hoàn thành, và provider có giới hạn riêng. Vì vậy tham số này giúp **giảm thời gian phản hồi**, nhưng không phải cơ chế enforcement với ngữ nghĩa tuyệt đối dưới mọi hình thức concurrency.

Không dùng skip-after-failure cho pipeline cần **tổng hợp toàn bộ test failures** để triage, vì nhiều lỗi sau có thể chưa được thực thi.

Khác với rerun:

- `skipAfterFailureCount` giảm phạm vi chạy **những test khác** sau lỗi.
- `rerunFailingTestsCount` tăng số attempts **của test đã lỗi** để xác định có hồi phục hay không.

Hai tham số có thể được sử dụng cùng nhau trong những phiên bản/provider Surefire hỗ trợ, nhưng tương tác và báo cáo cần kiểm chứng ở đúng version.

## 18. Kiểm thử thời gian: timeout không nên tạo flaky tests mới

JUnit Jupiter có assertions như:

~~~java
import static org.junit.jupiter.api.Assertions.assertTimeout;
import java.time.Duration;

assertTimeout(Duration.ofSeconds(2), () -> {
    int result = Calculator.divide(8, 4);
    assertEquals(2, result);
});
~~~

Đoạn này là **mảnh code minh họa đặt trong một test method**, không phải file Java độc lập. Nó giả định đã import `assertEquals` và có class `Calculator` trong scope.

Điểm cần chú ý:

- `assertTimeout` đo thời gian và báo thất bại nếu vượt giới hạn; cách thực thi của nó **không preemptive** theo nghĩa chủ động dừng code chậm ngay thời điểm timeout.
- `assertTimeoutPreemptively` dùng cách thực thi khác và có thể chạy code ở thread riêng; điều đó có thể ảnh hưởng đến thread-local state, transaction hoặc context.
- Không chọn timeout quá ngắn chỉ vì local laptop nhanh. CI runner chịu tải khác nhau có thể làm test chập chờn.
- Với unit test thuần logic, ưu tiên mock clock hoặc test deterministic thay vì đợi thời gian thật.
- Nếu ứng dụng có async code, test nên chờ completion đúng cách và truyền exception từ async task về test, không gọi `Thread.sleep` rồi đoán.

Nếu timeout là chính sách bảo vệ CI cho **toàn bộ fork JVM** hoặc deadlock, Surefire còn các tham số timeout/fork khác, không đồng nghĩa với JUnit assertion timeout.

## 19. Quarantine flaky test: tạm cách ly nhưng không quên

Khi một flaky test có ảnh hưởng lớn đến CI và chưa sửa ngay được, **quarantine** là lựa chọn tạm thời cần quản trị. Không nên âm thầm xóa test hoặc thêm `@Disabled` vô thời hạn.

Một quy trình tổ chức có thể yêu cầu:

1. Mở issue có owner, ngày bắt đầu và hạn xử lý.
2. Ghi loại flake, xác suất, môi trường và link report/CI runs.
3. Chỉ cách ly **một test hoặc nhóm rất hẹp** khỏi quality gate chính, không disable cả module.
4. Chạy quarantined tests trong **job độc lập** để vẫn thu thập tín hiệu.
5. Giới hạn thời gian cách ly; kiểm tra lại theo lịch và bỏ quarantine sau khi fix.
6. Không cho phép quarantined test che lỗi có mức độ an toàn/bảo mật nghiêm trọng mà không có quyết định cấp quyền rõ ràng.

Khi dùng JUnit tags:

~~~java
@Tag("quarantine")
@Test
void knownIntermittentScenario() {
    // kiểm tra scenario có vấn đề
}
~~~

Đây là **đoạn mã minh họa**, không phải một test hoàn chỉnh. Có thể cấu hình JUnit Platform hoặc Surefire để chọn/loại tag theo goal riêng. Đừng tự cho rằng một annotation `@Tag` **tự động** làm test bị skip; phải có cấu hình filter tương ứng, và report phải ghi rõ test thuộc quarantine.

**Phân biệt:** `@Disabled` làm test không chạy; `@Tag("quarantine")` chỉ gắn nhãn cho việc chọn lọc, nếu không có filter nó vẫn có thể chạy.

## 20. Chính sách CI đề xuất theo giai đoạn

Một tổ chức có thể chọn chính sách rõ ràng cho ba bước:

| Giai đoạn | Chính sách kiểm thử | Lý do |
| --- | --- | --- |
| PR/merge gate | Unit tests phải chạy và PASS; không ignore; có thể fail on first flake | Không cho regression đi vào main |
| Nightly/soak | Chạy lặp với seed và điều kiện biến thiên; ghi flake rate/report | Tìm flakiness và race trước khi tăng quy mô |
| Release gate | Phải có kết quả test hợp lệ và artifact đúng; không chấp nhận masked failures | Chặn phát hành khi tín hiệu chất lượng không đáng tin |

Một policy đơn giản có thể bắt đầu bằng:

~~~text
requiredUnitTestsExecuted > 0
unrecoveredFailures = 0
unrecoveredErrors = 0
allowedFlakes = 0
ignoredTestFailures = false
requiredTestReportPresent = true
~~~

Đây là **quy tắc chính sách khái niệm**, không phải file cấu hình Maven hay cú pháp expression của một CI platform. Các threshold cụ thể thuộc về tổ chức; có module đặc biệt không có unit tests và cần ngoại lệ có chứng cứ.

Nếu tổ chức dùng retry tạm thời để giảm noise, cần ghi rõ:

- Retry bao nhiêu lần?
- Test nào có quyền retry?
- Flake có làm PR fail không?
- Sau bao nhiêu ngày hoặc bao nhiêu lần flake thì phải sửa?
- Báo cáo XML/artifact được giữ và ai theo dõi?
- Có test nào tuyệt đối không được quarantine (security, dữ liệu tài chính, safety-critical)?

Không coi "retry tới khi PASS" là một chính sách kiểm thử đầy đủ.

## 21. Maven và CI exit code

Maven trả **process exit status** mà CI thường dùng để quyết định step thành công/thất bại. Trong chế độ mặc định:

~~~bash
mvn -B -ntp clean verify
~~~

nếu unit tests fail, Maven thông thường trả mã lỗi khác 0. CI cần đánh dấu pipeline/gate không đạt.

Ngược lại, nếu bật:

~~~bash
mvn -B -ntp clean verify -Dmaven.test.failure.ignore=true
~~~

thì Surefire có thể không làm build fail dù test đã đỏ. Một job dựa vào **exit code duy nhất** có thể hiểu sai mức độ an toàn nếu không đọc reports. Do đó chính sách nghiêm nên tránh ignore hoặc có bước phân tích reports độc lập có khả năng fail đúng.

Trong shell:

- Linux/macOS thường xem exit status của lệnh Maven qua `$?`.
- PowerShell có `$LASTEXITCODE` cho tiến trình native.
- CI platforms đọc exit status theo cơ chế riêng.

Đừng chạy trong script:

~~~bash
mvn clean verify || true
~~~

và coi đó là một gate hợp lệ. Dòng này ép shell bỏ qua lỗi; nếu cần giữ pipeline để upload report, phải để CI **ghi nhận bước test thất bại** và chỉ cho report-publishing step được chạy sau lỗi.

## 22. Module đa thành phần: fail policy đặt ở đâu?

Với multi-module Reactor:

~~~text
company-system/
├── pom.xml               (packaging pom)
├── api/pom.xml           (có unit tests)
├── service/pom.xml       (có unit tests)
└── bom/pom.xml           (packaging pom, không có test)
~~~

Nếu cấu hình `<failIfNoTests>true</failIfNoTests>` được áp dụng vô điều kiện cho **mọi module**, một module POM-only không có tests có thể tạo behavior không mong muốn khi Surefire được thực thi ở đó. Tốt hơn:

1. Quản lý **plugin version** và defaults trong parent `<pluginManagement>`.
2. Áp chính sách bắt buộc khi module có unit tests/được kỳ vọng phải có test.
3. Phân biệt module thư viện, application, BOM, aggregator và test-only modules.
4. Theo dõi test count **theo module** trong CI, không chỉ tổng Reactor.
5. Khi Maven `-pl` chỉ build một tập module, đừng coi kết quả đó là kiểm chứng toàn repo.
6. Nếu CI cần build cả dependency modules, dùng cấu hình Reactor phù hợp như `-am` khi cần.

Một module fail có thể khiến Reactor dừng hoặc skip những module khác theo chính sách fail mode. `-fae` (fail at end) giúp tiếp tục những module không phụ thuộc theo quy tắc Maven và tổng hợp lỗi, **không biến bài test lỗi thành PASS**. `-ff` (fail fast) dừng sớm hơn, còn `-fn` (fail never) có thể làm build tổng thể báo thành công bất chấp lỗi, nên không phù hợp làm gate release.

## 23. Test class naming và chạy một test cụ thể

Các lệnh hữu ích:

~~~bash
mvn -B -ntp test -Dtest=CalculatorTest
mvn -B -ntp test -Dtest=CalculatorTest#rejectsZeroDenominator
mvn -B -ntp clean test -Dtest=FailureGalleryTest -Ddemo.failure=true
~~~

Trên shell có cách diễn giải `#` đặc biệt, nếu bị shell xử lý như comment/fragment thì quote nguyên argument:

~~~bash
mvn -B -ntp test "-Dtest=CalculatorTest#rejectsZeroDenominator"
~~~

Một số plugin options:

- `includes`/`excludes` giới hạn lớp test theo patterns.
- `-Dtest=...` override chọn class/method khi chẩn đoán.
- `failIfNoSpecifiedTests` giúp phát hiện lệnh chọn test không match.
- JUnit `@Tag` + provider/filter chọn nhóm test theo tags.
- Maven profiles có thể định nghĩa các cấu hình chạy riêng cho smoke/slow tests; phải báo rõ phần nào thực sự được chạy.

Không dùng test selector hẹp trên release gate khi chính sách yêu cầu chạy **tất cả unit tests**.

## 24. Nếu Surefire không chạy được: không phải lỗi assertion

Phân biệt các lỗi ngoài test logic:

| Thông báo/tình huống | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `PluginResolutionException` | Không tải được Surefire hoặc plugin dependencies | Plugin repositories, mirror, server credentials |
| `Could not find artifact junit-jupiter` | Maven thiếu test dependency | repositories, dependency coordinates, release policy |
| Fork JVM terminated unexpectedly | Process crash, hết bộ nhớ, JVM options sai | Surefire dump/log, `argLine`, JDK, resources |
| `No tests were executed` | Naming/filter sai, no tests, provider không nhận | Includes/excludes, test annotations, `failIfNoTests` |
| `NoClassDefFoundError` trong test | Runtime test classpath thiếu hoặc lệch dependency | `dependency:tree`, classpath, reports |
| Tests PASS trên local nhưng FAIL trên CI | Locale/timezone/filesystem/cpu/network khác | Cố định môi trường, tránh global state |
| Tests chỉ fail khi chạy cả suite | Order/shared state/race | Isolation, cleanup, random/repeated runs |
| BUILD SUCCESS dù test FAIL | `testFailureIgnore`/Maven `-fn` hoặc CI ignore exit status | Kiểm tra invocation, cấu hình, report |

Không sửa tất cả lỗi bằng cách tăng timeout hoặc rerun. Nếu Surefire không khởi động được test JVM, `rerunFailingTestsCount` có thể không giải quyết root cause; nó được thiết kế chủ yếu cho **test case failure**, không phải mọi sự cố hạ tầng.

## 25. Tránh nhầm Surefire với Failsafe

Trong Maven, thường:

- **Surefire Plugin** chạy unit tests ở phase `test`.
- **Failsafe Plugin** chạy integration tests ở phases `integration-test` và `verify` khi được cấu hình.

Surefire thường phát hiện những tên như `*Test.java`; Failsafe thường dùng patterns như `*IT.java`, `*ITCase.java`. Đây là convention, không phải sự khác biệt duy nhất.

Nếu dùng Failsafe, không nên kết thúc CI tại `mvn integration-test` trong workflow Maven 3 cần cleanup và đánh giá kết quả ở `verify`. Dùng `mvn verify` để bao quát các steps đã được bind.

Các tham số ignore/skip/retry của Failsafe cần xem **goal và version đúng**. Không tự suy ra mọi property `skipTests` hoặc `rerunFailingTestsCount` của Surefire luôn map giống Failsafe phiên bản hiện hành.

Bài này chỉ đi sâu vào **độ tin cậy và failure policy của unit tests**; integration tests có thể cần policy bổ sung về external services, environment, long-running setup và cleanup.

## 26. Một chiến lược sửa flaky test, không chỉ retry

Giả sử một test xác minh thời gian:

~~~java
assertEquals("2026-11-10", service.currentDate());
~~~

Lỗi có thể do test phụ thuộc clock/timezone đang chạy. Cách cải tiến là **inject `Clock`** và cố định thời điểm/zone trong test.

Ví dụ mảnh code Java 17:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixed = Clock.fixed(
        Instant.parse("2026-11-10T00:00:00Z"),
        ZoneOffset.UTC
);
~~~

Sau đó code cần thời gian dùng `LocalDate.now(fixed)` thay vì `LocalDate.now()`. Đây là **đoạn minh họa** cho test design, không phải phần thêm vào project Calculator.

Một số chiến lược khác:

- Thay service thật bằng fake/mocked service khi đang viết **unit test**.
- Dùng `@TempDir` thay vì file path chung.
- Tách database transaction/fixtures cho từng test.
- Tránh static mutable state giữa test methods.
- Dùng `CompletableFuture.join/get` hoặc cơ chế đồng bộ phù hợp để chờ async operation thay vì ngủ một khoảng đoán mò.
- Với ngẫu nhiên, ghi seed và tái lập dữ liệu đầu vào.
- Bật parallel test chỉ khi code/test state đã được cách ly hoặc đồng bộ.
- Nếu một flaky test do bug concurrency thật, không chữa bằng serial-only mà không có issue kiểm soát; cần fix sản phẩm hoặc thiết kế test để phát hiện race đúng mục tiêu.

**Mục tiêu sửa** là test không còn phụ thuộc thứ tự và state ngoài ý định, chứ không chỉ nâng `rerunFailingTestsCount`.

## 27. Các kịch bản quyết định

### Kịch bản A: assertion failure mới xuất hiện sau commit

**Hành động:** fail PR gate; tái hiện bằng `-Dtest=...`, kiểm tra expected/actual, sửa code hoặc sửa kỳ vọng test có review. Không retry để che một failure deterministic.

### Kịch bản B: test fail một lần, rerun PASS

**Hành động:** ghi nhận flake, giữ XML/stack trace, mở issue; nếu policy nghiêm thì `failOnFlakeCount=1` để chặn PR. Không kết luận “đã hết lỗi” chỉ vì attempt cuối PASS.

### Kịch bản C: test không chạy mà pipeline xanh

**Hành động:** xem tên class, includes/excludes, `skipTests`/`maven.test.skip`, annotations và report count. Với module bắt buộc có tests, bật `failIfNoTests=true` và giám sát số tests thực thi.

### Kịch bản D: test phụ thuộc external API đôi khi lỗi

**Hành động:** đưa lời gọi API thật sang integration test; unit test dùng stub/fake. Nếu external behavior là hợp đồng cần kiểm tra, dùng Failsafe và môi trường có kiểm soát.

### Kịch bản E: test quá chậm nhưng vẫn ổn định

**Hành động:** đo profiling, tách fast unit tests khỏi integration tests, tối ưu fixtures. Đừng skip toàn bộ unit tests hoặc đặt `testFailureIgnore=true` để pipeline nhanh hơn.

### Kịch bản F: cần thu thập tất cả lỗi trong suite

**Hành động:** không bật skip-after-first quá sớm, hoặc dùng CI/nightly riêng để thu thập đầy đủ. Nếu dùng Maven Reactor, `-fae` có thể hỗ trợ tổng hợp module failures mà vẫn giữ trạng thái failed.

### Kịch bản G: pipeline có nhiều flakes lịch sử

**Hành động:** phân loại theo owner/root cause, đặt error budget/flaky threshold và hạn sửa; cách ly có chủ đích khi thật sự cần, đồng thời bắt buộc job theo dõi quarantined tests.

## 28. Bài tập tự kiểm tra có đáp án

1. **Code chủ động ném `IllegalArgumentException` và test dùng `assertThrows` đúng loại: PASS hay FAIL?**  
   **Đáp án:** PASS; đó là kiểm tra error path thành công.

2. **`assertEquals(5, Calculator.add(2, 2))` làm gì?**  
   **Đáp án:** Assertion failure, vì kết quả là `4`.

3. **Test tự ném `IllegalStateException` không được kỳ vọng?**  
   **Đáp án:** Test lỗi; Surefire thường ghi Error trong report tùy provider.

4. **Flaky test là test luôn FAIL?**  
   **Đáp án:** Không. Nó có thể PASS/FAIL không ổn định với điều kiện tương đương.

5. **`rerunFailingTestsCount=2` nghĩa là tổng cộng tối đa mấy attempts?**  
   **Đáp án:** Ba attempts gồm lần đầu và hai lần chạy lại.

6. **Một test fail rồi rerun PASS có nên được ghi nhận không?**  
   **Đáp án:** Có. Nó là flake, không chỉ là test PASS.

7. **`failOnFlakeCount=0` có phải zero tolerance không?**  
   **Đáp án:** Không. Giá trị 0 tắt ngưỡng fail theo số flake.

8. **Muốn Maven fail ngay khi có một flake được ghi nhận trên Surefire hỗ trợ?**  
   **Đáp án:** Dùng `rerunFailingTestsCount>0` cùng `failOnFlakeCount=1` và xác nhận report.

9. **Chạy `mvn clean test -Ddemo.failure=true` trong lab cho kết quả gì?**  
   **Đáp án:** Có hai test cố ý lỗi, build FAIL theo mặc định.

10. **Cờ `-Dmaven.test.failure.ignore=true` có làm test không chạy không?**  
    **Đáp án:** Không phải bản chất của cờ; nó cho phép bỏ qua hậu quả test failure đối với Maven build, không tương đương skip execution.

11. **`-DskipTests` và `-Dmaven.test.skip=true` có giống nhau không?**  
    **Đáp án:** Không. Cờ thứ hai có thể bỏ cả test compilation theo hỗ trợ của Compiler/Surefire.

12. **`failIfNoTests=true` có chắc bắt được cả suite mà mọi test bị `@Disabled` không?**  
    **Đáp án:** Không. Cần xem số test được execute/skipped trong reports.

13. **Vì sao demo flake cần `clean`?**  
    **Đáp án:** Để xóa marker dưới `target`; nếu marker còn, lần đầu có thể PASS.

14. **Trường hợp test chỉ FAIL khi chạy cả suite thường gợi ý gì?**  
    **Đáp án:** Test order, global state, shared fixtures, race hoặc cleanup lỗi.

15. **Có nên dùng `Thread.sleep(100)` để “chữa” mọi test async không?**  
    **Đáp án:** Không. Cần chờ sự kiện/thao tác hoàn thành đúng cách với timeout có kiểm soát.

16. **CI chỉ đọc Maven exit code nhưng Surefire bật failure ignore có thể hiểu sai điều gì?**  
    **Đáp án:** Build xanh dù test fail; phải kiểm tra flags và reports.

17. **Muốn chạy riêng `CalculatorTest` thì dùng gì?**  
    **Đáp án:** `mvn test -Dtest=CalculatorTest`.

18. **Surefire report mặc định thường nằm ở đâu?**  
    **Đáp án:** `target/surefire-reports`, có XML và text files.

19. **Phân biệt `-fae` và `-fn` trong Maven Reactor?**  
    **Đáp án:** `-fae` cố tiếp tục những module phù hợp và vẫn tổng hợp lỗi; `-fn` không phù hợp làm quality gate vì bỏ qua failure status.

20. **Giải pháp dài hạn cho flaky test là gì?**  
    **Đáp án:** Tìm root cause và làm test deterministic/isolation, không chỉ retry tới khi xanh.

## 29. Checklist chính sách thất bại cho dự án

- [ ] Dùng phiên bản JDK, Maven, Surefire, JUnit được khóa và kiểm tra tương thích.
- [ ] Unit tests nằm trong `src/test/java` và tên class khớp test discovery.
- [ ] Các assertion kiểm tra hợp đồng rõ ràng; exception dự kiến được xác nhận bằng `assertThrows`.
- [ ] Mỗi test độc lập với thứ tự chạy và state còn sót từ lần trước.
- [ ] Test không phụ thuộc clock/random/network thật khi không cần.
- [ ] `mvn clean test` hoặc `clean verify` được chạy trong CI theo policy.
- [ ] Test fail/error làm build FAIL, không bật failure ignore mặc định.
- [ ] `failIfNoTests` được bật ở module thật sự yêu cầu unit tests.
- [ ] CI giám sát số test thực thi, failures, errors, skipped và flakes.
- [ ] Nếu bật rerun, số lần thử được giới hạn và report giữ mọi attempts.
- [ ] `failOnFlakeCount` được đặt đúng ngưỡng; nhớ 0 = unlimited.
- [ ] Một flake có owner, issue, root-cause investigation và hạn sửa.
- [ ] Nếu quarantine, vẫn có job theo dõi và chính sách gỡ bỏ.
- [ ] Không dùng `skipTests` hoặc `maven.test.skip` để âm thầm qua gate.
- [ ] Test reports được upload ngay cả khi step thất bại mà không đổi trạng thái gate.
- [ ] Chỉ bật parallel execution sau khi kiểm tra isolation và race.
- [ ] Phân biệt Surefire unit tests với Failsafe integration tests.
- [ ] Kiểm tra đúng module Reactor và không dùng `-fn` trong release gate.
- [ ] Xóa/ẩn secret, URL nội bộ và dữ liệu khách hàng khỏi logs/reports.
- [ ] Không kết luận build an toàn chỉ vì lần cuối của flaky test PASS.

## Tài liệu chính thức

- [Apache Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/): goal `surefire:test`, lifecycle phase `test` và reports.
- [Surefire Goal Parameters](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html): `testFailureIgnore`, `failIfNoTests`, `failOnFlakeCount`, `rerunFailingTestsCount`, `skipAfterFailureCount` và các defaults.
- [Surefire — Rerun Failing Tests](https://maven.apache.org/surefire/maven-surefire-plugin/examples/rerun-failing-tests.html): reruns, flaky tests, report XML và tương tác ngưỡng flake.
- [Surefire — Skipping Tests After Failure](https://maven.apache.org/surefire/maven-surefire-plugin/examples/skip-after-failure.html): dừng sớm, giới hạn khi chạy parallel/forked.
- [Surefire — Skipping Tests](https://maven.apache.org/surefire/maven-surefire-plugin/examples/skipping-tests.html): phân biệt `skipTests` và `maven.test.skip`.
- [Surefire — Inclusion/Exclusion](https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion.html): tên test class và filter patterns.
- [Apache Maven — Introduction to Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phase `test`, `package`, `verify` và behavior Maven reactor.
- [JUnit 5 User Guide — Assertions](https://docs.junit.org/5.11.4/user-guide/): `assertThrows`, `assertEquals`, lifecycle, conditional test execution và test design.
- [JUnit User Guide — Conditional Test Execution](https://docs.junit.org/5.14.2/writing-tests/conditional-test-execution.html): `@EnabledIfSystemProperty`, `@Disabled` và những điều kiện runtime.
- [Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/): phân biệt integration test goals với Surefire.

**Kết luận:** Một unit test sai phải là **tín hiệu đỏ đáng tin**, một flaky test phải được **ghi nhận và sửa**, và một test không chạy phải được **nhìn thấy trong báo cáo**. Maven Surefire hỗ trợ fail policy, rerun và giới hạn flakes, nhưng không tự đưa ra chính sách chất lượng thay tổ chức. Hãy giữ test deterministic, giới hạn retry, bảo vệ CI exit status và luôn kiểm tra reports trước khi tuyên bố build đạt.

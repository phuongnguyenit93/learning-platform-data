# Báo cáo XML, tệp log và vị trí surefire-reports trong Maven

## 1. Vì sao phải đọc báo cáo thay vì chỉ nhìn BUILD SUCCESS?

Trong dự án Java dùng Maven, **Maven Surefire Plugin** thường chạy unit test ở phase `test` của default lifecycle. Ngoài thông báo trên terminal, Surefire ghi các báo cáo giúp con người và CI xác minh:

- Test nào đã chạy, tổng số test, số **failure**, **error** và **skipped**.
- Tên class/method thất bại, assertion message và stack trace để định vị lỗi.
- Dòng `System.out`/`System.err` hoặc log test đã được capture/redirect theo cấu hình.
- Những lỗi bất thường của JVM fork, timeout, stream hoặc test process.
- Kết quả của **đúng module và đúng lần build**, đặc biệt trong Maven Reactor nhiều module.
- Bằng chứng có thể lưu lại trên CI khi Maven trả exit code khác 0.

**Điểm quan trọng:** `BUILD SUCCESS` không bảo đảm đã có test chạy, nếu test bị skip hoặc plugin không tìm thấy test. Một file `TEST-*.xml` còn trên đĩa cũng không chứng minh **lần chạy vừa rồi** đã kiểm thử vì file có thể còn từ lượt build trước. Cần đối chiếu lệnh Maven, cấu hình Surefire, exit code và report được sinh mới.

Bài này giải thích chính xác **`target/surefire-reports`, cấu trúc XML/TXT, stdout/stderr và file dump**, kèm dự án Java 17 + JUnit 5 có thể chạy để tự tạo report PASS lẫn một failure có chủ đích.

## 2. Đường dẫn report mặc định trong một Maven project

Chạy từ thư mục chứa POM:

```bash
mvn -B clean test
```

Với một module Java tiêu chuẩn, Surefire ghi mặc định vào:

```text
<project-basedir>/target/surefire-reports/
```

Parameter cấu hình đường dẫn là `reportsDirectory`, mặc định `${project.build.directory}/surefire-reports`. Trong đa số project, `project.build.directory` là `target`; nếu POM đổi build directory hoặc Surefire reportsDirectory, vị trí report sẽ khác.

Ví dụ test class có tên `demo.surefire.ArithmeticTest`:

```text
surefire-report-lab/
├── pom.xml
├── src/
│   ├── main/java/demo/surefire/Arithmetic.java
│   └── test/java/demo/surefire/ArithmeticTest.java
└── target/
    ├── classes/
    ├── test-classes/
    └── surefire-reports/
        ├── TEST-demo.surefire.ArithmeticTest.xml
        └── demo.surefire.ArithmeticTest.txt
```

Cặp file có tiền tố `TEST-` và đuôi `.xml` phục vụ **máy đọc**; file `.txt` cung cấp **tóm tắt văn bản**. Nếu test thực hiện stdout và POM bật redirect, thư mục có thể chứa file `*-output.txt` nữa.

### 2.1. Các loại file và cách sử dụng

| Đường dẫn/tên file | Vai trò | Có luôn tồn tại không? |
| --- | --- | --- |
| `target/surefire-reports/TEST-*.xml` | Báo cáo unit test dạng XML; CI thường đọc | Khi Surefire chạy và XML reporter được bật/ghi thành công |
| `target/surefire-reports/*.txt` | Báo cáo text theo test suite | Thường có khi báo cáo file bật |
| `target/surefire-reports/*-output.txt` | Đầu ra test được redirect ra file | **Không**: cần `redirectTestOutputToFile` và có output |
| `target/surefire-reports/*.dump` | Dữ liệu chẩn đoán Surefire trong tình huống đặc biệt | Không phải mỗi build |
| `target/surefire-reports/*.dumpstream` | Dữ liệu dòng giao tiếp/test process bất thường | Không phải mỗi build |
| `target/failsafe-reports/` | Báo cáo integration test của Failsafe | Chỉ khi Failsafe đã cấu hình/chạy |
| `target/site/` hoặc báo cáo HTML riêng | Site/report plugin tổng hợp kết quả | Không tự xuất hiện chỉ vì `mvn test` |
| Maven/CI console log | Log Maven toàn bộ build, gồm compiler/test/plugin | Do terminal/CI thu, không phải `TEST-*.xml` |

Không đồng nhất `target/test-classes` với `target/surefire-reports`: thư mục đầu chứa **class test đã biên dịch**, thư mục sau chứa **kết quả thực thi**.

## 3. Thứ tự lifecycle: report chỉ xuất hiện khi Surefire được chạy

Với project `jar` và default lifecycle phù hợp:

```text
process-resources       → resources:resources
compile                 → compiler:compile
process-test-resources  → resources:testResources
test-compile            → compiler:testCompile
test                    → surefire:test  → surefire-reports
package                 → jar:jar
verify                  → các goal kiểm chứng được cấu hình
```

Ý nghĩa đối với việc tìm report:

- `mvn test` chạy các phase trước `test` và thường thực thi `surefire:test`.
- `mvn verify` đi qua phase test; tuy nhiên việc Failsafe/integration test có chạy không còn phụ thuộc POM.
- `mvn test-compile` chỉ biên dịch test, **không phải lời xác nhận test đã chạy**.
- `mvn compiler:testCompile` chỉ gọi trực tiếp goal biên dịch test, không chạy Surefire.
- `mvn surefire:test` gọi goal trực tiếp nhưng không tự chạy mọi phase trước đó; nếu dự án thiếu class/resources chưa được build, có thể fail theo cách khác.
- `mvn clean test` xóa output cũ trước khi chạy, giúp báo cáo dễ quy về lượt hiện tại.

**Phân biệt lỗi trước test:** nếu Maven Compiler Plugin thất bại ở `compile` hoặc `test-compile`, Surefire chưa chạy và không có XML mới. Khi đó phải đọc lỗi compiler chứ không cố tìm file report chưa được tạo.

## 4. XML: tệp TEST-*.xml chứa những gì?

Surefire báo cáo XML thường theo cấu trúc JUnit-style XML. Tên file bao gồm test suite/class; nội dung có phần tổng kết và testcase.

Mẫu sau **minh họa cấu trúc** một test class có ba case, trong đó một case fail, không phải output nguyên văn của một JDK/Surefire cụ thể:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="demo.surefire.ArithmeticTest"
           tests="3" errors="0" failures="1"
           skipped="0" time="0.025">
    <testcase name="sumsNumbers"
              classname="demo.surefire.ArithmeticTest"
              time="0.004"/>
    <testcase name="rejectsZeroDivisor"
              classname="demo.surefire.ArithmeticTest"
              time="0.006"/>
    <testcase name="failsOnlyWhenRequested"
              classname="demo.surefire.ArithmeticTest"
              time="0.015">
        <failure type="org.opentest4j.AssertionFailedError"
                 message="Intentional failure for report practice">
            Example stack trace text
        </failure>
    </testcase>
</testsuite>
```

Đây là XML có cấu trúc mẫu để học; các giá trị thời gian và message do test runtime thực tế xác định, và `Example stack trace text` **không** phải stack trace được lấy từ lệnh Maven.

### 4.1. Ý nghĩa các attribute chính

| Trường | Định nghĩa thực hành | Cách kiểm tra |
| --- | --- | --- |
| `tests` | Tổng số testcase được báo cáo trong suite | Phải khớp với tập test có chủ đích |
| `failures` | Những test thất bại do assertion/điều kiện test | Xem `<failure>`, expected/actual |
| `errors` | Exception hoặc lỗi không thuộc assertion failure thông thường | Xem `<error>`, root cause |
| `skipped` | Những test case bị bỏ qua theo framework/provider | Không tính như pass |
| `time` | Thời gian được plugin báo, thường tính bằng giây | Gợi ý chậm, không phải benchmark |
| `name` của `testsuite` | Tên suite/class | Đối chiếu đúng module/class |
| `name` của `testcase` | Tên case/method | Tìm mã test tương ứng |
| `classname` | Class chứa testcase | Hữu ích khi nhiều suite cùng tên |
| `<failure>` | Thông điệp, loại assertion, stack trace | Xem nơi assertion fail |
| `<error>` | Lỗi thực thi bất ngờ, stack trace | Kiểm tra môi trường và code |
| `<skipped>` | Thông tin skip, nếu provider ghi | Điều tra vì sao case chưa chạy |
| `<system-out>`/`<system-err>` | Console output được report lưu khi có | Phụ trợ debug, cần bảo vệ dữ liệu nhạy cảm |
| `<properties>` | Một số property của test runtime nếu plugin ghi | Có thể chứa thông tin nhạy cảm |

Công thức trực giác trong suite đơn giản: `passed = tests - failures - errors - skipped`. Tuy vậy, nếu Surefire chạy **rerun failing tests**, báo cáo thêm flaky/rerun nodes hoặc provider có quy ước riêng, cần parser hiểu schema tương ứng. Không tự cộng những số này để ra quyết định cuối cùng khi có retry phức tạp.

### 4.2. Phân biệt failure, error và skipped

**Failure** thường là assertion không đạt:

```java
assertEquals(10, 2 + 3);
```

Đoạn này là **ví dụ Java của một assertion sai**, không phải test runnable chính của bài. Test engine có thể ghi `AssertionFailedError` vào `<failure>`.

**Error** thường là lỗi ngoài assert, chẳng hạn code ném `NullPointerException` trong setup/run/teardown:

```java
String text = null;
System.out.println(text.length());
```

Đây cũng chỉ là đoạn minh họa, có thể ném exception khi chạy. Cách framework phân loại một loại exception cụ thể còn phụ thuộc engine/provider và phiên bản.

**Skipped** có thể do `@Disabled`, assumptions, condition hoặc cơ chế riêng của runner; XML có thể ghi `<skipped/>`. Đừng nhầm skipped case với **toàn bộ test goal bị skip** bởi `-DskipTests`: khi cả goal bị skip, thường không có report mới cho các case.

## 5. Báo cáo TXT không phải toàn bộ Maven build log

Cùng test class, Surefire thường tạo file văn bản:

```text
target/surefire-reports/demo.surefire.ArithmeticTest.txt
```

Trong đó có thể có tóm tắt:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0, Time elapsed: ... s
```

Đây là **mô hình trình bày**, không phải output cố định. `reportFormat` có thể chọn `brief` hoặc `plain` đối với file text; Surefire 3.2.5 có giá trị mặc định `brief`.

**TXT** giúp mở nhanh để đọc tên test và lỗi; **XML** thích hợp cho parser CI/JUnit test results. Console log Maven lại chứa cả quá trình tải artifact, chạy compiler, phase, plugin version, lỗi POM và những thông tin không nhất thiết có trong TXT.

Khi báo cáo một lỗi, nên cung cấp **tên suite/case + XML failure/error + đường dẫn file + lệnh build**; không chỉ đính một đoạn text từ console rồi bỏ qua artifact.

## 6. Dòng System.out và System.err của test được ghi ở đâu?

Test có thể in:

```java
System.out.println("DEMO_STDOUT_MARKER");
System.err.println("DEMO_STDERR_MARKER");
```

Nhưng cách Surefire hiển thị những dòng đó tùy cấu hình/provider/fork:

- Có thể xuất hiện ở terminal.
- Có thể được capture trong XML (những thẻ `system-out`/`system-err`).
- Khi bật redirect, stdout có thể đi vào file `<testName>-output.txt`.
- Log của SLF4J/Log4j/Logback còn phụ thuộc backend, appender và cấu hình framework; không nhất thiết đi theo cùng đường với `System.out`.
- Lỗi JVM fork/crash có thể khiến output bị cắt hoặc đi vào tệp chẩn đoán riêng.

Surefire 3.2.5 có parameter chính thức:

```xml
<redirectTestOutputToFile>true</redirectTestOutputToFile>
```

Tài liệu goal giải thích khi true, **stdout của unit test** được chuyển đến file trong `reportsDirectory` theo mẫu `testName-output.txt`. User property tương ứng là `maven.test.redirectTestOutputToFile`.

Ví dụ lệnh:

```bash
mvn -B -Dmaven.test.redirectTestOutputToFile=true clean test
```

**Mặc định** `redirectTestOutputToFile=false`, vì vậy đừng yêu cầu `*-output.txt` xuất hiện ở mọi build. Ngay cả khi bật redirect, không được khẳng định file đó chứa **toàn bộ** log Maven, stack trace XML và mọi logging framework message.

## 7. Các tệp .dump, .dumpstream và lỗi JVM fork

Một assertion fail thông thường **không nhất thiết tạo dump**. Những file như `*.dump`, `*.dumpstream` có thể xuất hiện khi Surefire gặp sự cố giao tiếp với forked JVM, stream bất thường, tiến trình bị dừng ngoài dự kiến hoặc tình huống chẩn đoán khác.

Mẫu tên **minh họa**, không phải tên chuẩn cho mọi phiên bản:

```text
target/surefire-reports/<timestamp>-jvmRun1.dump
target/surefire-reports/<timestamp>-jvmRun1.dumpstream
```

Cách xử lý:

1. Đọc **Maven console error** và exit code trước.
2. Tìm file dump thực sự được sinh, không tự đoán timestamp/name.
3. Đối chiếu với `TEST-*.xml` có/không có; crash có thể xảy ra trước khi báo cáo kịp được hoàn thiện.
4. Kiểm tra Java/JDK, `forkCount`, memory/timeout, native libraries, process kill và có code gọi `System.exit` không.
5. Nếu JVM crash ở tầng native, file như `hs_err_pid*.log` có thể nằm ở working directory hoặc vị trí `-XX:ErrorFile`, **không phải XML/TXT của Surefire**.

Nếu không có dump, đừng suy ra Surefire không có lỗi: một lỗi compile trước phase `test` cũng không tạo Surefire dump.

**Bảo mật:** dump và stack trace có thể chứa đường dẫn, token, hostnames hoặc dữ liệu nghiệp vụ. Chỉ chia sẻ trong phạm vi cho phép, có retention/permissions phù hợp.

## 8. Cấu hình quan trọng của Surefire 3.2.5

| Parameter | Default / công dụng | User property nếu plugin công bố |
| --- | --- | --- |
| `reportsDirectory` | `${project.build.directory}/surefire-reports` | Nên cấu hình bằng POM khi muốn đổi vị trí |
| `useFile` | `true`; điều khiển tạo file report thay vì chỉ report ra console | `surefire.useFile` |
| `reportFormat` | `brief`; có `plain` cho **TXT**, không chọn format XML | `surefire.reportFormat` |
| `printSummary` | `true`; in tóm tắt ở console | `surefire.printSummary` |
| `redirectTestOutputToFile` | `false`; true cho `*-output.txt` | `maven.test.redirectTestOutputToFile` |
| `reportNameSuffix` | Rỗng; có thể thêm suffix vào XML/TXT/output filename | `surefire.reportNameSuffix` |
| `trimStackTrace` | `false` ở 3.2.5; rút ngắn stack trace trong report nếu bật | `trimStackTrace` |
| `rerunFailingTestsCount` | `0`; cho phép chạy lại test fail theo quy tắc Surefire | `surefire.rerunFailingTestsCount` |
| `failIfNoTests` | `false` ở 3.2.5; true để không chấp nhận không có test | `failIfNoTests` |
| `failIfNoSpecifiedTests` | `true`; khi `-Dtest` không khớp test thì fail | `surefire.failIfNoSpecifiedTests` |

Các giá trị theo tài liệu **Surefire 3.2.5**, không được mặc định giữ nguyên ở mọi plugin version sau này.

### 8.1. Đổi thư mục report

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.2.5</version>
    <configuration>
        <reportsDirectory>${project.build.directory}/unit-test-results</reportsDirectory>
    </configuration>
</plugin>
```

Đây là **đoạn POM**, không phải file đầy đủ. Nếu áp dụng, CI phải tìm ở `target/unit-test-results` thay vì `target/surefire-reports` mặc định.

### 8.2. reportNameSuffix làm đổi tên file

```xml
<reportNameSuffix>unit</reportNameSuffix>
```

Có thể tạo tên như:

```text
TEST-demo.surefire.ArithmeticTest-unit.xml
demo.surefire.ArithmeticTest-unit.txt
```

Pattern `TEST-*.xml` vẫn thường phù hợp nhưng đường dẫn hardcode tới một filename cố định có thể sai.

### 8.3. printSummary và reportFormat khác nhau

`printSummary` điều khiển phần tổng kết console; `reportFormat` thay cách trình bày TXT; `redirectTestOutputToFile` xử lý stdout test; `reportsDirectory` chọn thư mục đích. **Không cái nào trong số này là “nút làm test pass”.**

Parameter `disableXmlReport` đã deprecated ở Surefire 3.x; nếu không có XML, ưu tiên tìm đúng cấu hình reporter và version thay vì bật/tắt tùy tiện một tham số cũ.

## 9. Ví dụ runnable Java 17, Maven và JUnit Jupiter

Ta tạo một project có **4 test trong 2 class**. Lượt chạy mặc định PASS, còn một lượt chạy có cờ `-Ddemo.injectFailure=true` làm đúng một test FAIL để học cách đọc báo cáo. Sau đó ta khôi phục bằng clean build.

### 9.1. Cấu trúc file

```text
surefire-report-lab/
├── pom.xml
└── src/
    ├── main/java/demo/surefire/Arithmetic.java
    └── test/java/demo/surefire/
        ├── ArithmeticTest.java
        └── OutputTest.java
```

Yêu cầu JDK 17+, Maven có thể chạy các plugin đã pin và repository được phép tải dependency JUnit.

### 9.2. POM hoàn chỉnh

Tệp `surefire-report-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>surefire-report-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <demo.injectFailure>false</demo.injectFailure>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
                <configuration>
                    <reportsDirectory>${project.build.directory}/surefire-reports</reportsDirectory>
                    <useFile>true</useFile>
                    <reportFormat>plain</reportFormat>
                    <printSummary>true</printSummary>
                    <redirectTestOutputToFile>true</redirectTestOutputToFile>
                    <failIfNoTests>true</failIfNoTests>
                    <systemPropertyVariables>
                        <demo.injectFailure>${demo.injectFailure}</demo.injectFailure>
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
```

POM này quan trọng ở những điểm sau:

- `<reportsDirectory>` dùng đường dẫn mặc định nhưng ghi rõ để dễ học.
- `useFile=true` và `reportFormat=plain` bật text report rõ ràng.
- `redirectTestOutputToFile=true` cho phép xem `*-output.txt`.
- `failIfNoTests=true` ngăn pass khi không có test nào.
- `systemPropertyVariables` đưa property `demo.injectFailure` vào JVM mà Surefire dùng để chạy test. Giá trị mặc định là `false`; người dùng có thể dùng `-Ddemo.injectFailure=true` để thay đúng một lần.
- Compiler Plugin biên dịch Java với `--release 17`; JUnit ở test scope, không cần ở runtime sản phẩm.
- Các phiên bản được chọn nhằm giữ ví dụ nhất quán, **không phải khẳng định bản mới nhất**.

### 9.3. Mã sản phẩm Arithmetic.java

Tệp `src/main/java/demo/surefire/Arithmetic.java`:

```java
package demo.surefire;

public final class Arithmetic {
    private Arithmetic() {
    }

    public static int add(int a, int b) {
        return Math.addExact(a, b);
    }

    public static int divide(int a, int b) {
        if (b == 0) {
            throw new IllegalArgumentException("divisor must not be zero");
        }
        return a / b;
    }

    public static void main(String[] args) {
        System.out.println("3 + 4 = " + add(3, 4));
    }
}
```

Chương trình là Java 17 hợp lệ. `Math.addExact` kiểm tra overflow, nhưng dữ liệu 3 và 4 không bị tràn. Code sản phẩm không dùng JUnit hay thư viện ngoài lúc runtime.

### 9.4. ArithmeticTest.java: 3 test và một điểm fail có kiểm soát

Tệp `src/test/java/demo/surefire/ArithmeticTest.java`:

```java
package demo.surefire;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ArithmeticTest {
    @Test
    void sumsNumbers() {
        assertEquals(7, Arithmetic.add(3, 4));
    }

    @Test
    void rejectsZeroDivisor() {
        IllegalArgumentException exception = assertThrows(
                IllegalArgumentException.class,
                () -> Arithmetic.divide(12, 0));
        assertEquals("divisor must not be zero", exception.getMessage());
    }

    @Test
    void failsOnlyWhenRequested() {
        boolean requested = Boolean.parseBoolean(
                System.getProperty("demo.injectFailure", "false"));
        assertFalse(requested,
                "Intentional failure for Surefire report practice");
    }
}
```

Ở lệnh Maven bình thường, property là `false` nên cả ba test pass. Khi truyền `-Ddemo.injectFailure=true`, Surefire nhận giá trị qua `systemPropertyVariables`, test thứ ba fail với assertion message rõ ràng. Không cần sửa mã nguồn hoặc tạo file đặc biệt.

### 9.5. OutputTest.java: một test có stdout và stderr

Tệp `src/test/java/demo/surefire/OutputTest.java`:

```java
package demo.surefire;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OutputTest {
    @Test
    void printsDiagnosticLines() {
        System.out.println("DEMO_STDOUT_MARKER");
        System.err.println("DEMO_STDERR_MARKER");
        assertEquals("ready", "ready");
    }
}
```

Có **4 test tổng cộng**: ba test ở ArithmeticTest và một test ở OutputTest. Marker là dữ liệu minh họa an toàn, không phải password hay thông tin người dùng.

### 9.6. Chạy lượt PASS và xác minh các file

Tại thư mục `surefire-report-lab/`:

```bash
mvn -version
mvn -B clean test
```

Nếu môi trường hợp lệ, Surefire chạy **4 tests, 0 failures, 0 errors, 0 skipped**. Các file quan trọng dự kiến:

```text
target/surefire-reports/
├── TEST-demo.surefire.ArithmeticTest.xml
├── TEST-demo.surefire.OutputTest.xml
├── demo.surefire.ArithmeticTest.txt
├── demo.surefire.OutputTest.txt
└── demo.surefire.OutputTest-output.txt
```

Trong XML ArithmeticTest dự kiến `tests=3`, `failures=0`, `errors=0`, `skipped=0`. Trong XML OutputTest dự kiến `tests=1` với ba bộ đếm lỗi/skip đều bằng 0.

File `demo.surefire.OutputTest-output.txt` giúp xem marker `DEMO_STDOUT_MARKER` khi redirect đã hoạt động; xem thêm cách stderr được ghi trong runtime cụ thể. Một run bình thường không phải tạo dump file.

Chạy riêng class sản phẩm:

```bash
java -cp target/classes demo.surefire.Arithmetic
```

**Stdout chính xác của lệnh Java này:**

```text
3 + 4 = 7
```

`java -cp ...` ở đây không chạy Surefire và không sinh test report mới.

### 9.7. Cố tình tạo một failure và đọc XML

Chạy:

```bash
mvn -B -Ddemo.injectFailure=true clean test
```

Đây là **bài thực hành cố ý thất bại**. Kỳ vọng:

- ArithmeticTest: 3 tests, **1 failure** do `failsOnlyWhenRequested`.
- OutputTest: 1 test pass.
- Toàn project: **4 tests, 1 failure, 0 errors, 0 skipped**.
- Maven trả exit code khác 0 và báo `BUILD FAILURE` do assertion fail.
- Surefire thường ghi các file XML/TXT của những suite đã chạy dù build fail.

Mở file:

```text
target/surefire-reports/TEST-demo.surefire.ArithmeticTest.xml
target/surefire-reports/demo.surefire.ArithmeticTest.txt
```

Tìm `<testcase name="failsOnlyWhenRequested" ...>` và `<failure>` để xem message, exception type, stack trace và file/method gây fail. Các dấu `...` trong câu này chỉ là văn bản tóm tắt, **không phải literal XML đầy đủ**.

Không coi đây là lỗi của Maven compiler hoặc cấu hình repository: kết quả fail được thiết kế để cho người học thực hành đọc report.

### 9.8. Khôi phục trạng thái PASS

Sau thí nghiệm, chạy **không mang cờ gây fail**:

```bash
mvn -B clean verify
```

`clean` xóa report cũ, POM trả `demo.injectFailure=false`, và 4 test dự kiến đều pass. Phải kiểm tra report mới và exit code; đừng chỉ khẳng định đã sửa sau khi xóa một file lỗi.

## 10. Mở report bằng command line

### 10.1. Linux/macOS

```bash
# Liệt kê file hiện có
find target/surefire-reports -maxdepth 1 -type f -print

# Xem báo cáo dạng text
cat target/surefire-reports/*.txt

# Tìm marker stdout
grep -R "DEMO_STDOUT_MARKER" target/surefire-reports

# Xem nhanh nơi có failure hoặc error
grep -n "failure\\|error" target/surefire-reports/TEST-*.xml
```

`grep` chỉ tìm chuỗi; khi cần đếm test chính xác, nên dùng XML parser. Lệnh có thể trả exit code 1 nếu không tìm thấy từ khóa — điều đó không đồng nghĩa Maven build fail.

### 10.2. Windows PowerShell

```powershell
Get-ChildItem -LiteralPath target\surefire-reports -File
Get-Content -LiteralPath target\surefire-reports\demo.surefire.ArithmeticTest.txt

Get-ChildItem -Path target\surefire-reports -Filter 'TEST-*.xml' -File |
    ForEach-Object {
        [xml]$xml = Get-Content -LiteralPath $_.FullName -Raw
        [PSCustomObject]@{
            Suite    = [string]$xml.testsuite.name
            Tests    = [int]$xml.testsuite.tests
            Failures = [int]$xml.testsuite.failures
            Errors   = [int]$xml.testsuite.errors
            Skipped  = [int]$xml.testsuite.skipped
        }
    }
```

`[xml]` dùng XML parser của .NET, đọc thuộc tính thay vì tách text. Ví dụ này dùng cấu trúc XML thông thường với root `testsuite`; nếu provider/report version dùng namespace hoặc dạng `testsuites` khác, cần điều chỉnh parser.

Để tìm marker:

```powershell
Get-ChildItem -Path target\surefire-reports -File |
    Select-String -Pattern 'DEMO_STDOUT_MARKER'
```

Không in toàn bộ report nhạy cảm lên CI console công khai.

### 10.3. Script Python 3 để cộng thống kê XML

Một script chuẩn hóa kết quả mà không cần thư viện ngoài, lưu thành file `report_summary.py` bên cạnh `pom.xml` khi thực hành:

```python
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

directory = (
    Path(sys.argv[1])
    if len(sys.argv) > 1
    else Path("target/surefire-reports")
)
files = sorted(directory.glob("TEST-*.xml"))
if not files:
    print(f"NO REPORTS in {directory}")
    sys.exit(2)

totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}

for file in files:
    root = ET.parse(file).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    for suite in suites:
        counts = {
            key: int(suite.get(key, "0"))
            for key in totals
        }
        for key, value in counts.items():
            totals[key] += value
        print(f"{suite.get('name')}: {counts}")

print("TOTAL:", totals)
if totals["failures"] or totals["errors"]:
    sys.exit(1)
```

Lệnh dùng:

```bash
python3 report_summary.py target/surefire-reports
```

Với demo sau lượt PASS, dòng cuối kỳ vọng:

```text
TOTAL: {'tests': 4, 'failures': 0, 'errors': 0, 'skipped': 0}
```

Hai dòng trước mô tả từng suite. Với Windows, có thể dùng `python` thay `python3` nếu launcher chỉ đăng ký tên đó.

**Giới hạn:** đây là công cụ học tập cho XML thông thường, không phải validator tổng quát cho rerun/flaky tests, XML namespaces phức tạp hoặc artifact stale. CI thực tế nên sử dụng parser JUnit XML đã được hỗ trợ và kiểm chứng.

## 11. HTML report không phải do Surefire test goal mặc định tạo

**Surefire Plugin** chạy test, tạo XML và TXT. **Surefire Report Plugin** là plugin riêng có thể đọc `TEST-*.xml` để tạo báo cáo HTML:

```bash
mvn -B clean test
mvn org.apache.maven.plugins:maven-surefire-report-plugin:3.2.5:report-only
```

Goal `report-only` **không chạy lại test**; nó dùng kết quả đã có. Phiên bản Surefire Report Plugin phải được xác nhận tồn tại/tương thích với Maven/JDK và repository thực tế; không suy ra một plugin version từ plugin khác chỉ vì tên tương tự.

Tùy plugin version và cách gọi standalone/site, HTML có thể xuất hiện ở thư mục như `target/reports` hoặc `target/site`. Đọc goal documentation và `outputDirectory` của plugin version đang dùng thay vì hardcode một path chung.

Nếu cần HTML nhưng Maven build test bị fail, pipeline có thể chạy bước report generation theo một stage có điều kiện phù hợp và giữ report XML; đừng bỏ bước thu XML chỉ vì HTML chưa có.

**Máy CI** thường đọc JUnit XML để tính trend; **người đọc** dùng TXT/HTML để quan sát thuận tiện. Mỗi loại có mục đích khác nhau.

## 12. Maven Reactor nhiều module: mỗi module có report riêng

Giả sử:

```text
project-root/
├── pom.xml
├── core/pom.xml
├── service/pom.xml
└── web/pom.xml
```

Lệnh:

```bash
mvn -B clean verify
```

có thể tạo:

```text
core/target/surefire-reports/TEST-*.xml
service/target/surefire-reports/TEST-*.xml
web/target/surefire-reports/TEST-*.xml
```

Root `packaging=pom` **có thể không có report**, vì nó không có test class. Đừng coi thư mục root thiếu `target/surefire-reports` là lỗi khi những module có test đã chạy đúng.

Khi dùng:

```bash
mvn -pl :service -am test
```

`-am` có thể đưa thêm module cần build vào Reactor và những module đó có thể chạy test của mình. Phải xác minh **đúng module** mà report thuộc về; test count ở `core` không phải test count của `service`.

Trong build song song `-T`, console log giữa các module có thể xen nhau; report tách theo basedir thường đáng tin hơn để tìm suite gây lỗi. Không cấu hình nhiều module ghi cùng một thư mục tuyệt đối khi không có cơ chế tránh trùng tên và tranh chấp file.

## 13. Surefire vs Failsafe: unit test và integration test

- **Surefire Plugin:** thường dùng unit tests ở phase `test`, mặc định ghi `target/surefire-reports`.
- **Failsafe Plugin:** thường dùng integration tests với goal `integration-test` và `verify` sau khi đã khai báo execution; mặc định ghi `target/failsafe-reports`.

Ví dụ **đoạn POM bổ sung**, không nằm trong ví dụ runnable ở phần 9:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.2.5</version>
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

Không có `maven-failsafe-plugin` và test integration phù hợp trong POM thì `mvn verify` **không tự tạo failsafe-reports**. Nếu CI muốn tổng hợp cả hai nhóm, phải thu hai đường dẫn khác nhau và xem có test bị chạy trùng giữa hai plugin không.

## 14. CI: thu báo cáo kể cả khi Maven trả exit code khác 0

Một pipeline đúng cần:

1. Chạy test **không skip**, ghi nhận Maven/JDK, lệnh và exit code.
2. Thu tất cả XML mới của những module được chọn.
3. Cho CI publish chúng theo parser JUnit XML chính thức.
4. Lưu TXT, output log và dump nếu có — **cả khi job fail**.
5. Đảm bảo không trộn report từ các run khác nhau.
6. Kiểm soát quyền truy cập/retention vì report có thể chứa dữ liệu nhạy cảm.

Ví dụ **glob** cho artifact collection (không phải lệnh shell trực tiếp):

```text
**/target/surefire-reports/TEST-*.xml
**/target/surefire-reports/*.txt
**/target/surefire-reports/*.dump
**/target/surefire-reports/*.dumpstream
**/target/failsafe-reports/TEST-*.xml
```

Khi project đổi `reportsDirectory`, những glob này **phải được cập nhật**. Nếu job archive artifacts chỉ chạy trên success, lần test fail có thể mất ngay bằng chứng cần để debug.

Với CI yêu cầu unit test, nên kiểm tra **non-zero test count** và có XML parse hợp lệ. Surefire `failIfNoTests=true` có thể hỗ trợ, nhưng không phải module nào cũng cần test (ví dụ parent POM). Thiết kế policy theo module thay vì bật bắt buộc cho toàn bộ parent mà không xét thực tế.

### 14.1. Test report cũ có thể làm CI xanh/đỏ sai

Trường hợp:

- Hôm qua `OldTest` fail và để lại `TEST-demo.OldTest.xml`.
- Hôm nay chỉ chạy một test subset bằng `-Dtest=NewTest`, không chạy `clean`.
- CI upload toàn bộ `target/surefire-reports/*.xml`, kể cả file cũ.

Pipeline có thể báo kết quả không phản ánh lượt chạy hiện tại. Giải pháp là **clean đúng output trước test**, thu XML theo job/run, không trộn artifact cũ. Nếu cần preserve report trước clean, archive vào artifact CI trước khi workspace bị xóa.

Một build `mvn -B clean verify` cuối cùng sau thí nghiệm failure là cách hợp lý để chứng minh các báo cáo hiện tại đều thuộc lượt PASS.

### 14.2. Đừng làm lộ dữ liệu trong log test

XML có thể ghi Java system properties; test stdout, error message hoặc dump có thể in credential, path nội bộ, hostname, dữ liệu thật. Tránh log secrets, đừng upload công khai report và giữ retention/ACL phù hợp.

Chỉ bật Maven `-X` để debug khi cần, vì debug log thường dài và có thể chứa cấu hình môi trường. Không đưa token hoặc password lên CLI khi không có cơ chế bảo vệ và không chia sẻ file report chưa rà soát.

## 15. Khi không thấy XML hoặc TXT, nên điều tra theo thứ tự nào?

| Dấu hiệu | Khả năng nguyên nhân | Bước kiểm chứng |
| --- | --- | --- |
| `target/surefire-reports` không tồn tại | Test chưa chạy, bị skip hoặc path được đổi | Lệnh Maven, POM `reportsDirectory`, log phase |
| Compiler fail trước test | Surefire chưa chạy | Xem compiler error, không tìm XML mới |
| `BUILD SUCCESS` nhưng không có test case | Không phát hiện test hoặc test bị skip | Naming pattern, `failIfNoTests`, skip flags |
| Có TXT nhưng không có XML | XML reporter bị tắt/đổi | Kiểm tra Surefire report configuration |
| Có XML nhưng không có TXT | Reporter/useFile config khác mặc định | Xem `useFile`, version, file output |
| Không có `*-output.txt` | Chưa bật redirect hoặc test không in stdout | `redirectTestOutputToFile`, test code |
| File XML có tên lạ | `reportNameSuffix`, provider, class name | Liệt kê directory, tìm `TEST-*.xml` |
| XML của lỗi hôm trước vẫn còn | Workspace/cache chưa clean | `mvn clean test`, thu đúng run |
| XML nói `skipped` nhưng không fail | `@Disabled`, assumption hoặc điều kiện test | Đọc node `skipped`, code |
| Maven fail nhưng XML chưa phản ánh | Fork crash/timeout, lỗi trước reporter | Console, dump, JVM logs |
| CI không có test trend | Artifact glob sai, chưa publish JUnit XML | Config CI và file tại workspace |
| Root thiếu report | Parent POM không có unit test | Tìm ở các module con |
| HTML không xuất hiện | Chưa chạy Surefire Report Plugin | Phân biệt report HTML với XML |
| Lỗi `Failed to execute goal surefire:test` | Có test fail hoặc plugin/fork lỗi | Đọc exception gốc, XML/TXT/dump |
| Report XML parser lỗi | File bị cắt, hỏng encoding, format khác | Dùng XML parser, không chỉ grep |

Trình tự điều tra ngắn:

1. Kiểm tra Maven command, exit code và tên module.
2. Xác định goal `maven-surefire-plugin:<version>:test` có thực sự chạy không.
3. Kiểm tra `skipTests`, `maven.test.skip`, `-Dtest=...`, profile và naming.
4. Xác định `reportsDirectory` theo POM hiệu lực.
5. Liệt kê file thật, mở XML/TXT và đọc testcase.
6. Nếu XML không đầy đủ, tìm lỗi fork, dump, JVM logs và lỗi ở phase trước.
7. Chạy lại `mvn -B clean test` trong môi trường có quyền/khả năng debug phù hợp.
8. Sau khi sửa, xác nhận cả **exit code** và **report mới**, không chỉ xóa file cũ.

## 16. Checklist review kết quả test

- [ ] POM pin Surefire Plugin version và dùng đúng tài liệu parameter?
- [ ] Lệnh Maven có thật sự chạy phase `test`, không skip?
- [ ] Report directory được xác định theo **đúng module**?
- [ ] XML `TEST-*.xml` mới được sinh, có thể parse và tổng số test đúng kế hoạch?
- [ ] `failures` và `errors` ở mức được policy chấp nhận?
- [ ] `skipped` được đánh giá rõ, không tự xem là pass?
- [ ] Với fail/error, đã đọc tên testcase, message và stack trace?
- [ ] File TXT được dùng như báo cáo phụ trợ, không thay thế XML machine parsing?
- [ ] Khi cần test stdout, đã kiểm tra `redirectTestOutputToFile` và vị trí `*-output.txt`?
- [ ] Nếu có fork issue, đã thu dump/dumpstream và console error?
- [ ] CI archive report cả khi Maven fail và không trộn build cũ?
- [ ] Nếu dùng Failsafe, báo cáo integration test có được thu riêng?
- [ ] Report không lộ secrets hoặc nội dung chỉ dành cho môi trường nội bộ?
- [ ] Kết quả cuối đã được xác minh từ một **clean build** và exit code thật?

**Kết luận:** Surefire lưu kết quả unit test theo mặc định ở **`target/surefire-reports`**. `TEST-*.xml` là nguồn dữ liệu cho CI, `*.txt` là bản tóm tắt đọc nhanh, `*-output.txt` chứa output test khi bật redirect, còn `*.dump`/`*.dumpstream` hỗ trợ chẩn đoán sự cố đặc biệt. Hiểu đúng loại file, vị trí theo module và thời điểm sinh report giúp tránh nhầm “không có báo cáo” với “test đã pass”, đồng thời giúp kiểm chứng chất lượng build một cách tái lập.

### Tài liệu chính thức

- [Apache Maven Surefire Plugin — Introduction](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Maven Surefire Plugin 3.2.5 — surefire:test parameters](https://maven.apache.org/surefire-archives/surefire-3.2.5/maven-surefire-plugin/test-mojo.html)
- [Maven Surefire Plugin — Using Console Logs](https://maven.apache.org/surefire/maven-surefire-plugin/examples/logging.html)
- [Maven Surefire Plugin — Using System Properties](https://maven.apache.org/surefire/maven-surefire-plugin/examples/system-properties.html)
- [Maven Surefire Plugin — Using JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Maven Surefire Report Plugin — Report và Report-only](https://maven.apache.org/surefire/maven-surefire-report-plugin/)
- [Maven Failsafe Plugin — integration-test reportsDirectory](https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)

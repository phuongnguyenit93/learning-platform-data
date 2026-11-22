# Ghi nhận stdout, stderr và tạo báo cáo kiểm thử XML

Khi chạy kiểm thử Java bằng Apache Ant, thông tin hữu ích không chỉ nằm ở kết quả pass hoặc fail. Test có thể ghi log chẩn đoán qua `System.out`, ghi cảnh báo hoặc lỗi qua `System.err`, và cần tạo báo cáo có cấu trúc để CI lưu trữ hoặc hiển thị kết quả.

Task `<junit>` của Ant hỗ trợ thu thập đầu ra của test và chuyển dữ liệu đó đến log hoặc formatter. Khi kết hợp với formatter XML, mỗi test suite có thể tạo một file báo cáo chứa số lượng test, thời gian chạy, failure, error và phần output được thu thập.

## 1. Phân biệt stdout và stderr

Trong Java, hai luồng đầu ra chuẩn thường được sử dụng như sau:

```java
System.out.println("Test started");
System.err.println("Could not load test fixture");
```

- `System.out` là standard output (stdout), thường dành cho thông tin kết quả hoặc tiến trình.
- `System.err` là standard error (stderr), thường dành cho cảnh báo và thông tin lỗi.

Hai luồng này độc lập. Khi chạy ứng dụng từ terminal, shell có thể chuyển hướng chúng riêng biệt. Khi chạy test qua Ant, task `<junit>` có thể thu thập output từ test process và quyết định hiển thị trong log Ant, chuyển cho formatter, hoặc cả hai.

Ví dụ test JUnit 4:

```java
package com.example;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class AppTest {

    @Test
    public void printsDiagnostics() {
        System.out.println("Starting calculation test");
        System.err.println("Diagnostic: using default test input");

        assertEquals(5, 2 + 3);
    }
}
```

Khi chạy test, hai dòng được ghi vào hai luồng khác nhau. Nếu không cấu hình thu thập output phù hợp, người đọc có thể chỉ thấy summary test mà không thấy những thông tin chẩn đoán này trong báo cáo XML.

## 2. Điều kiện để dùng task junit

Task `<junit>` là optional task của Ant. Môi trường build cần có thư viện task `ant-junit` và thư viện JUnit mà test sử dụng. Với ví dụ dưới đây, giả sử dự án dùng JUnit 4 và có các JAR cần thiết trong thư mục `lib`.

Ví dụ cấu trúc:

```text
sample-app/
├── build.xml
├── lib/
│   ├── junit-4.13.2.jar
│   └── hamcrest-core-1.3.jar
├── src/
│   ├── main/java/com/example/App.java
│   └── test/java/com/example/AppTest.java
├── build/
│   ├── classes/
│   ├── test-classes/
│   └── reports/
└── dist/
```

JAR JUnit/Hamcrest là dependency của test project. `ant-junit` là thư viện cung cấp task `<junit>` cho Ant và cần có trên classpath của Ant, thường được đặt trong thư mục `ANT_HOME/lib` cùng các thư viện Ant khác. Hai nhóm JAR này có vai trò khác nhau.

Ví dụ này sử dụng JUnit 4. Task `<junit>` cổ điển của Ant không tự động trở thành runner tương thích với mọi test JUnit 5. Nếu dự án dùng JUnit 5, cần dùng JUnit Platform Console Launcher hoặc một runner/integration phù hợp rồi gọi runner qua Ant.

## 3. Cấu hình classpath cho test

JUnit cần tìm thấy class ứng dụng, class test và thư viện test. Có thể tạo một `path` để tái sử dụng:

```xml
<path id="test.classpath">
    <pathelement location="build/classes"/>
    <pathelement location="build/test-classes"/>
    <fileset dir="lib">
        <include name="junit-*.jar"/>
        <include name="hamcrest-*.jar"/>
    </fileset>
</path>
```

`path` mô tả classpath, còn task `<junit>` sử dụng nó bằng `<classpath refid="test.classpath"/>`. Nếu test dùng thêm thư viện khác, bổ sung JAR tương ứng vào classpath. Không nên đưa dependency test vào artifact runtime nếu ứng dụng không cần chúng khi chạy.

## 4. Thu thập stdout và stderr bằng task junit

Hai thuộc tính quan trọng của task `<junit>` là `showoutput` và `outputtoformatters`:

| Thuộc tính | Tác dụng |
|---|---|
| `showoutput="true"` | Hiển thị output của test trong log Ant |
| `outputtoformatters="true"` | Chuyển output của test đến các formatter được cấu hình, chẳng hạn formatter XML |

Mặc định, output của test không nhất thiết được hiển thị hoặc ghi vào formatter. Nếu muốn vừa xem stdout/stderr trong log build vừa đưa output vào báo cáo XML, bật cả hai thuộc tính.

```xml
<junit fork="true"
       printsummary="yes"
       showoutput="true"
       outputtoformatters="true">
    <classpath refid="test.classpath"/>
    <formatter type="xml" usefile="true"/>
    <test name="com.example.AppTest" todir="build/reports"/>
</junit>
```

Trong ví dụ:

- `fork="true"` chạy test trong JVM riêng.
- `showoutput="true"` gửi output của test vào log Ant.
- `outputtoformatters="true"` chuyển output đến formatter.
- `formatter type="xml"` chọn XML formatter.
- `usefile="true"` ghi kết quả formatter ra file.
- `todir` xác định thư mục báo cáo cho test được chạy.

Nếu chỉ muốn lưu output trong XML để CI đọc mà không làm log terminal quá dài, có thể đặt `showoutput="false"` và giữ `outputtoformatters="true"`. Nếu muốn output xuất hiện ở cả hai nơi, bật cả hai.

## 5. Tạo báo cáo XML cho một test class

Với một lớp test cụ thể, dùng nested element `<test>`:

```xml
<target name="test-one">
    <mkdir dir="build/reports"/>

    <junit fork="true"
           printsummary="yes"
           showoutput="true"
           outputtoformatters="true">
        <classpath refid="test.classpath"/>
        <formatter type="xml" usefile="true"/>
        <test name="com.example.AppTest"
              todir="build/reports"/>
    </junit>
</target>
```

Ant chạy lớp `com.example.AppTest` và formatter XML tạo báo cáo trong `build/reports`. Với XML formatter chuẩn, tên file báo cáo thường theo dạng `TEST-com.example.AppTest.xml`.

Báo cáo XML thường chứa thông tin suite như:

- Tên test suite và tên test class.
- Số lượng test, failure và error.
- Tổng thời gian thực thi.
- Stack trace và message của assertion failure hoặc test error.
- Các phần tử output như `system-out` và `system-err` nếu output được chuyển đến formatter.

Tên và cấu trúc chi tiết có thể phụ thuộc formatter và phiên bản Ant. Các hệ thống CI thường nhận diện định dạng JUnit XML theo quy ước tên file và cấu trúc report tương thích.

## 6. Tạo XML report cho nhiều test class bằng batchtest

Trong dự án thực tế, không nên khai báo từng lớp test thủ công nếu có thể chọn chúng bằng fileset. Nested element `<batchtest>` cho phép chạy nhiều test class được tìm thấy trong thư mục class đã biên dịch:

```xml
<target name="test">
    <mkdir dir="build/reports"/>

    <junit fork="true"
           printsummary="yes"
           showoutput="true"
           outputtoformatters="true">
        <classpath refid="test.classpath"/>
        <formatter type="xml" usefile="true"/>

        <batchtest todir="build/reports">
            <fileset dir="build/test-classes">
                <include name="**/*Test.class"/>
                <exclude name="**/Abstract*.class"/>
            </fileset>
        </batchtest>
    </junit>
</target>
```

`batchtest` quét các class phù hợp với fileset và chạy chúng như các test suite. XML formatter tạo report cho từng test class được thực thi. Có thể điều chỉnh mẫu include/exclude theo quy ước đặt tên test của dự án.

Không chọn class tiện ích hoặc abstract test base nếu chúng không phải test suite có thể chạy. Một fileset quá rộng có thể khiến JUnit cố chạy các class không phù hợp và sinh lỗi khởi tạo test.

## 7. Hiểu các formatter

Task `<junit>` hỗ trợ nhiều formatter. Một số loại thường gặp:

| Formatter | Mục đích | Cách sử dụng |
|---|---|---|
| `plain` | Báo cáo dạng văn bản dễ đọc | Hữu ích cho log hoặc file text |
| `brief` | Tóm tắt ngắn, tập trung vào kết quả | Hữu ích khi muốn giảm log |
| `xml` | Báo cáo có cấu trúc theo định dạng JUnit XML | Phù hợp cho CI và công cụ phân tích test |

Ví dụ có thể cấu hình cả XML formatter và plain formatter:

```xml
<junit fork="true"
       printsummary="yes"
       showoutput="true"
       outputtoformatters="true">
    <classpath refid="test.classpath"/>
    <formatter type="plain" usefile="false"/>
    <formatter type="xml" usefile="true"/>
    <batchtest todir="build/reports">
        <fileset dir="build/test-classes">
            <include name="**/*Test.class"/>
        </fileset>
    </batchtest>
</junit>
```

Formatter `plain` với `usefile="false"` gửi phần trình bày dạng văn bản tới log thay vì tạo file riêng. Formatter XML vẫn ghi report ra file. Khi có nhiều formatter, `outputtoformatters="true"` chuyển output của test đến các formatter đã cấu hình; hãy cân nhắc lượng dữ liệu được ghi để tránh report quá lớn.

## 8. Điều khiển output để log không quá dài

Không phải dự án nào cũng muốn in toàn bộ stdout và stderr của mọi test vào terminal. Với một bộ test lớn, log có thể rất dài và làm lu mờ thông tin lỗi.

Một cấu hình thường phù hợp cho CI là giữ output trong XML nhưng không in tất cả ra log Ant:

```xml
<junit fork="true"
       printsummary="yes"
       showoutput="false"
       outputtoformatters="true">
    <classpath refid="test.classpath"/>
    <formatter type="xml" usefile="true"/>
    <batchtest todir="build/reports">
        <fileset dir="build/test-classes">
            <include name="**/*Test.class"/>
        </fileset>
    </batchtest>
</junit>
```

Kết quả summary vẫn được in theo cấu hình `printsummary`, còn output test được chuyển tới XML formatter. Người vận hành có thể mở report của suite lỗi để đọc `system-out` và `system-err`.

Nếu cần xem output trực tiếp khi debug một test, tạm bật `showoutput="true"` hoặc chạy riêng test class đó. Không nên mặc định bật log chi tiết cho toàn bộ suite nếu lượng output lớn.

## 9. Phân biệt test failure và test error

Trong JUnit, failure thường là assertion không đạt; error thường là ngoại lệ hoặc lỗi thực thi không được xem là assertion failure. Task `<junit>` có thể ghi nhận hai loại trạng thái riêng.

Các thuộc tính hữu ích:

- `failureproperty`: đặt property khi có test failure.
- `errorproperty`: đặt property khi có test error.
- `haltonfailure`: dừng build khi có failure.
- `haltonerror`: dừng build khi có error.

Để vẫn tạo report và sau đó dừng với thông báo riêng, có thể không dừng ngay tại task JUnit mà ghi nhận hai property trước:

```xml
<target name="test">
    <junit fork="true"
           printsummary="yes"
           showoutput="false"
           outputtoformatters="true"
           haltonfailure="false"
           haltonerror="false"
           failureproperty="tests.failed"
           errorproperty="tests.error">
        <classpath refid="test.classpath"/>
        <formatter type="xml" usefile="true"/>
        <batchtest todir="build/reports">
            <fileset dir="build/test-classes">
                <include name="**/*Test.class"/>
            </fileset>
        </batchtest>
    </junit>

    <fail if="tests.error"
          message="Test execution encountered an error. Inspect the XML reports in build/reports."/>
    <fail if="tests.failed"
          message="One or more tests failed. Inspect the XML reports in build/reports."/>
</target>
```

Trong cấu hình này, JUnit task có thể hoàn tất việc ghi report sau khi chạy test. Sau đó Ant kiểm tra các property và dừng build với thông báo phù hợp. Property failure/error được đặt khi loại vấn đề tương ứng xuất hiện; `if` kiểm tra sự tồn tại của property đó.

Nếu không cần thông báo riêng hoặc xử lý bổ sung, có thể đặt `haltonfailure="true"` và `haltonerror="true"` để yêu cầu task dừng build ngay khi gặp lỗi tương ứng. Hãy chọn một chiến lược rõ ràng, tránh vừa dừng sớm vừa mong đợi một bước tổng hợp phía sau luôn chạy.

## 10. Ví dụ test tạo cả stdout và stderr

Một test đơn giản có thể ghi output rồi kiểm tra kết quả:

```java
package com.example;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class CalculatorTest {

    @Test
    public void addsNumbers() {
        System.out.println("Running addsNumbers");
        System.err.println("Input values: 2 and 3");

        int result = 2 + 3;

        assertEquals(5, result);
    }

    @Test
    public void reportsFailure() {
        System.out.println("Running reportsFailure");
        System.err.println("Expected value is 10");

        assertEquals("The result must be 10", 10, 2 + 3);
    }
}
```

Test thứ nhất pass; test thứ hai tạo assertion failure. Với `showoutput="true"`, các dòng output có thể được nhìn thấy trong log Ant. Với `outputtoformatters="true"` và XML formatter, output được chuyển đến report để người đọc xem cùng kết quả suite.

Trong ví dụ minh họa, test thứ hai cố tình fail. Không giữ assertion sai trong bộ test phát hành; hãy dùng nó để quan sát cách report ghi nhận failure, sau đó sửa hoặc loại test thử nghiệm.

## 11. Đọc cấu trúc JUnit XML

XML formatter tạo dữ liệu có cấu trúc. Một report rút gọn có thể trông như sau:

```xml
<testsuite name="com.example.CalculatorTest"
           tests="2"
           failures="1"
           errors="0"
           time="0.012">
    <testcase classname="com.example.CalculatorTest"
              name="addsNumbers"
              time="0.004"/>
    <testcase classname="com.example.CalculatorTest"
              name="reportsFailure"
              time="0.008">
        <failure message="The result must be 10" type="java.lang.AssertionError">
            ... stack trace ...
        </failure>
    </testcase>
    <system-out><![CDATA[Running addsNumbers
Running reportsFailure]]></system-out>
    <system-err><![CDATA[Input values: 2 and 3
Expected value is 10]]></system-err>
</testsuite>
```

Đây là hình minh họa rút gọn về cấu trúc thường gặp, không phải nội dung cố định của mọi phiên bản formatter. Trong report thật, có thể có thêm properties, thời gian, thông tin test case, stack trace và metadata khác.

Các trường thường được hệ thống CI sử dụng:

- `tests`: tổng số test case.
- `failures`: số assertion failure.
- `errors`: số test error.
- `time`: thời gian thực thi.
- `<failure>` hoặc `<error>`: chi tiết test không thành công.
- `<system-out>` và `<system-err>`: output chuẩn và output lỗi được formatter ghi nhận.

Nếu XML không có `system-out` hoặc `system-err`, hãy kiểm tra `outputtoformatters`, test có thực sự ghi ra luồng đó không và formatter đang được cấu hình ra sao.

## 12. Tổ chức thư mục báo cáo và dọn output cũ

Nên lưu report trong một thư mục ổn định như `build/reports/junit`. Trước mỗi lần chạy, có thể xóa report cũ để CI không vô tình đọc nhầm kết quả từ lần trước.

```xml
<property name="reports.dir" location="${basedir}/build/reports/junit"/>

<target name="prepare-reports">
    <delete dir="${reports.dir}"/>
    <mkdir dir="${reports.dir}"/>
</target>

<target name="test" depends="prepare-reports">
    <junit fork="true"
           printsummary="yes"
           showoutput="false"
           outputtoformatters="true"
           haltonfailure="false"
           haltonerror="false"
           failureproperty="tests.failed"
           errorproperty="tests.error">
        <classpath refid="test.classpath"/>
        <formatter type="xml" usefile="true"/>
        <batchtest todir="${reports.dir}">
            <fileset dir="build/test-classes">
                <include name="**/*Test.class"/>
            </fileset>
        </batchtest>
    </junit>

    <fail if="tests.error"
          message="JUnit reported test errors. See ${reports.dir}."/>
    <fail if="tests.failed"
          message="JUnit reported test failures. See ${reports.dir}."/>
</target>
```

Trong ví dụ, report cũ được xóa trước khi test chạy. Đây là lựa chọn phù hợp khi thư mục báo cáo chỉ chứa output sinh ra từ một lần chạy. Nếu CI cần lưu lịch sử, hãy để CI archive report sau mỗi job hoặc tạo thư mục riêng theo build identifier thay vì giữ file cũ trong cùng thư mục.

Không xóa thư mục source hoặc thư mục chứa artifact phát hành trong target chuẩn bị report. Chỉ dọn đúng thư mục output được dành riêng cho test.

## 13. Tích hợp report XML với CI

Hầu hết CI có khả năng đọc định dạng JUnit XML hoặc có plugin để thu thập report. Ant chỉ cần tạo report vào một thư mục ổn định; pipeline sẽ cấu hình bước publish test results trỏ đến mẫu file tương ứng.

Ví dụ cấu trúc artifact của job:

```text
build/reports/junit/
├── TEST-com.example.AppTest.xml
├── TEST-com.example.CalculatorTest.xml
└── TEST-com.example.RepositoryTest.xml
```

Tên file thực tế phụ thuộc tên test class và formatter. Trong CI, dùng glob phù hợp với quy ước của Ant, chẳng hạn `build/reports/junit/TEST-*.xml`.

Nên lưu report kể cả khi test thất bại. Cấu hình task JUnit với `haltonfailure="false"`/`haltonerror="false"`, ghi property và gọi `<fail>` sau đó là một cách để report được tạo trước khi build kết thúc thất bại. Pipeline CI cũng nên được cấu hình để thu thập report khi job thất bại, không chỉ khi thành công.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không nhận diện task `<junit>` | Thiếu optional task library `ant-junit` hoặc chưa nạp task | Kiểm tra cài đặt Ant và classpath của Ant |
| Không tìm thấy `org.junit.Test` | JUnit JAR không có trong test classpath | Bổ sung JUnit vào `test.classpath` |
| Test chạy nhưng XML không có stdout/stderr | Chưa bật `outputtoformatters` hoặc test không ghi output | Bật `outputtoformatters="true"` và kiểm tra `System.out`/`System.err` |
| Terminal không hiển thị output test | `showoutput` đang false | Bật `showoutput="true"` khi cần debug trực tiếp |
| Log quá dài | Hiển thị output của tất cả test | Tắt `showoutput`, giữ output trong formatter XML |
| Không có report cho một test class | Fileset không chọn class hoặc class không phải test hợp lệ | Kiểm tra `build/test-classes` và include pattern |
| CI hiển thị 0 test | CI trỏ sai thư mục hoặc sai glob XML | Kiểm tra `todir`, tên file report và pattern publish |
| CI đọc report cũ | Không dọn report trước lần chạy mới | Xóa thư mục output hoặc dùng thư mục riêng cho mỗi job |
| Build dừng trước bước tổng hợp report | `haltonfailure` hoặc `haltonerror` bật quá sớm | Ghi property, để task hoàn tất report rồi fail ở bước sau |

## 15. Bài tập thực hành

1. Tạo hai test JUnit 4: một test pass và một test cố tình fail.
2. Cho mỗi test ghi một dòng qua `System.out` và một dòng qua `System.err`.
3. Chạy `<junit>` với `showoutput="true"` để quan sát output trong log Ant.
4. Bật `outputtoformatters="true"` và formatter XML, sau đó mở report để tìm `system-out` và `system-err`.
5. Đặt `showoutput="false"` nhưng giữ `outputtoformatters="true"`; xác nhận output vẫn có thể được lưu trong report mà không in toàn bộ ra log Ant.
6. Chuyển từ `<test>` sang `<batchtest>` để chạy nhiều test class.
7. Dùng `failureproperty` và `errorproperty`, đặt `haltonfailure`/`haltonerror` false rồi dừng bằng `<fail>` sau khi report được tạo.
8. Xóa report cũ trước khi chạy và cấu hình CI thu thập `TEST-*.xml`.
9. Sửa test cố tình fail, chạy lại và xác nhận số failure trong XML về 0.

Sau bài tập, người học cần giải thích được khác biệt giữa `showoutput` và `outputtoformatters`, cách XML formatter lưu kết quả, vai trò của `batchtest`, và cách bảo đảm report vẫn được tạo trước khi build kết thúc thất bại.

## 16. Nguyên tắc áp dụng trong dự án

Giữ stdout/stderr có mục đích: chỉ ghi thông tin hữu ích cho chẩn đoán, không in secret hoặc dữ liệu nhạy cảm. Dùng `showoutput` để quyết định có đưa output vào log Ant hay không; dùng `outputtoformatters` để đưa output đến XML formatter. Tạo report vào thư mục riêng, xóa hoặc phân tách report cũ và cấu hình CI thu thập XML kể cả khi test thất bại.

Với test suite lớn, ưu tiên để XML lưu chi tiết từng suite và giữ log terminal ở mức summary. Khi một test lỗi, người phát triển có thể mở report tương ứng để xem assertion, stack trace, stdout và stderr mà không phải tìm giữa hàng nghìn dòng log.

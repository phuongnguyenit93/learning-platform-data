# Chạy JUnit 3 hoặc JUnit 4 bằng task junit trong Apache Ant

Apache Ant cung cấp task `<junit>` để chạy các bài kiểm thử viết bằng JUnit ngay trong buildfile. Task này hỗ trợ cả phong cách JUnit 3 dựa trên `junit.framework.TestCase` và JUnit 4 dựa trên annotation như `@Test`. Có thể chạy một lớp test riêng lẻ hoặc quét một tập lớp test theo mẫu, tạo báo cáo và quyết định build có tiếp tục khi test thất bại hay không.

Để dùng task này, dự án cần chuẩn bị đúng thư viện JUnit và thư viện task tùy chọn của Ant, biên dịch mã nguồn test, rồi khai báo classpath chứa lớp ứng dụng, lớp test và JUnit.

## 1. JUnit 3 và JUnit 4 khác nhau ở đâu?

Cả JUnit 3 và JUnit 4 đều cung cấp assertion để kiểm tra kết quả, nhưng cách tổ chức lớp test khác nhau.

### 1.1. JUnit 3: kế thừa TestCase và đặt tên phương thức test

JUnit 3 dùng lớp `junit.framework.TestCase`. Lớp test thường kế thừa TestCase và các phương thức kiểm thử có tên bắt đầu bằng `test`.

Ví dụ:

~~~java
package com.example;

import junit.framework.TestCase;

public class CalculatorTest extends TestCase {

    public void testAdd() {
        assertEquals(5, Calculator.add(2, 3));
    }

    public void testSubtract() {
        assertEquals(3, Calculator.subtract(7, 4));
    }
}
~~~

Đặc điểm thường gặp của JUnit 3:

- Lớp test kế thừa `TestCase`.
- Phương thức kiểm thử là phương thức `public`, không nhận tham số và có tên bắt đầu bằng `test`.
- Có thể dùng `setUp()` để chuẩn bị dữ liệu trước mỗi test và `tearDown()` để giải phóng tài nguyên sau mỗi test.
- Có thể tạo test suite bằng phương thức tĩnh `suite()`.

Ví dụ dùng setUp và tearDown:

~~~java
public class CalculatorTest extends TestCase {
    private Calculator calculator;

    @Override
    protected void setUp() throws Exception {
        super.setUp();
        calculator = new Calculator();
    }

    public void testAdd() {
        assertEquals(9, calculator.add(4, 5));
    }

    @Override
    protected void tearDown() throws Exception {
        calculator = null;
        super.tearDown();
    }
}
~~~

### 1.2. JUnit 4: dùng annotation

JUnit 4 bổ sung annotation để đánh dấu test và các phương thức vòng đời. Lớp test không bắt buộc phải kế thừa TestCase.

~~~java
package com.example;

import org.junit.Test;
import static org.junit.Assert.assertEquals;

public class CalculatorJUnit4Test {

    @Test
    public void addsTwoNumbers() {
        assertEquals(5, Calculator.add(2, 3));
    }

    @Test
    public void subtractsTwoNumbers() {
        assertEquals(3, Calculator.subtract(7, 4));
    }
}
~~~

Một số annotation thường dùng:

| Annotation | Vai trò |
|---|---|
| `@Test` | Đánh dấu phương thức kiểm thử |
| `@Before` | Chạy trước mỗi phương thức test |
| `@After` | Chạy sau mỗi phương thức test |
| `@BeforeClass` | Chạy một lần trước các test trong lớp |
| `@AfterClass` | Chạy một lần sau các test trong lớp |
| `@Ignore` | Tạm bỏ qua test hoặc lớp test |
| `@RunWith` | Chọn runner JUnit tùy chỉnh |

JUnit 4 cũng hỗ trợ các lớp JUnit 3 kế thừa TestCase. Ant có thể chạy các test JUnit 4 thuần dùng annotation mà không cần bọc bằng `JUnit4TestAdapter`.

## 2. Chuẩn bị thư viện cho task junit

Task `<junit>` là task tùy chọn của Ant và phụ thuộc vào thư viện ngoài. Cần có:

- `ant-junit.jar`: chứa phần tích hợp JUnit của Ant.
- `junit.jar`: thư viện JUnit tương ứng với phiên bản test đang dùng.
- Các thư viện phụ thuộc khác của phiên bản JUnit đã chọn, nếu có; ví dụ JUnit 4.13.2 thường được dùng cùng Hamcrest.

Có một số cách cung cấp các JAR này cho Ant:

1. Đặt cả `ant-junit.jar` và JUnit JAR trong thư mục `ANT_HOME/lib`.
2. Thêm cả hai JAR vào classpath môi trường hoặc dùng tùy chọn `-lib` khi gọi Ant.
3. Khai báo classpath trong phần `taskdef` của buildfile để Ant nạp task tùy chọn.
4. Từ Ant 1.7, có thể giữ `ant-junit.jar` ở vị trí mặc định trong `ANT_HOME/lib` và đưa JUnit JAR vào classpath lồng bên trong task `<junit>`.

Ví dụ gọi Ant với thư viện bổ sung:

~~~bash
ant -lib lib/ant-junit.jar -lib lib/junit-4.13.2.jar test
~~~

Tên file và đường dẫn cần thay theo phiên bản thư viện thực tế. Nếu dùng JUnit 4.13.2 và cần các API assertion dựa trên Hamcrest, hãy đưa JAR Hamcrest tương ứng vào classpath của test.

**Phân biệt hai classpath:** Ant phải tìm được task implementation `ant-junit.jar` để nhận biết phần tử `<junit>`; còn classpath lồng trong task cung cấp JUnit và các lớp mà test cần khi chạy. Khi dùng fork, classpath đó cũng được truyền cho JVM con theo cấu hình của task.

Nếu Ant báo không nhận diện được task `junit`, hãy kiểm tra `ant-junit.jar`. Nếu task đã chạy nhưng báo không tìm thấy `org.junit.Test` hoặc `junit.framework.TestCase`, hãy kiểm tra JUnit JAR trong classpath test.

## 3. Chuẩn bị cấu trúc thư mục và classpath

Một dự án Java có thể tổ chức mã nguồn và test như sau:

~~~text
inventory/
├── build.xml
├── lib/
│   ├── junit-4.13.2.jar
│   └── hamcrest-core-1.3.jar
├── src/
│   ├── main/
│   │   └── java/
│   │       └── com/example/Calculator.java
│   └── test/
│       └── java/
│           └── com/example/
│               ├── CalculatorTest.java
│               └── CalculatorJUnit4Test.java
└── build/
    ├── classes/
    ├── test-classes/
    └── reports/
~~~

Khai báo các property và Path:

~~~xml
<project name="inventory" default="test" basedir=".">
    <property name="src.main" location="src/main/java" />
    <property name="src.test" location="src/test/java" />
    <property name="build.main" location="build/classes" />
    <property name="build.test" location="build/test-classes" />
    <property name="reports.dir" location="build/reports/junit" />
    <property name="junit.jar" location="lib/junit-4.13.2.jar" />
    <property name="hamcrest.jar" location="lib/hamcrest-core-1.3.jar" />

    <path id="test.compile.classpath">
        <pathelement location="${build.main}" />
        <pathelement location="${junit.jar}" />
        <pathelement location="${hamcrest.jar}" />
    </path>

    <path id="test.runtime.classpath">
        <pathelement location="${build.main}" />
        <pathelement location="${build.test}" />
        <pathelement location="${junit.jar}" />
        <pathelement location="${hamcrest.jar}" />
    </path>
</project>
~~~

Classpath biên dịch test cần có:

- Thư mục lớp ứng dụng để test gọi được mã cần kiểm thử.
- JUnit để compiler nhận biết TestCase, annotation và assertion.
- Các thư viện khác mà test hoặc ứng dụng phụ thuộc.

Classpath chạy test cũng cần thư mục chứa các lớp test đã biên dịch. Tách hai Path theo mục đích giúp tránh nhầm lẫn giữa compile-time và runtime.

## 4. Biên dịch mã nguồn ứng dụng và test trước khi chạy

Task `<junit>` chạy các lớp đã được biên dịch. Vì vậy, build thường có target biên dịch ứng dụng, target biên dịch test và target chạy test.

~~~xml
<target name="compile">
    <mkdir dir="${build.main}" />

    <javac srcdir="${src.main}"
           destdir="${build.main}"
           includeantruntime="false"
           encoding="UTF-8" />
</target>

<target name="compile-test" depends="compile">
    <mkdir dir="${build.test}" />

    <javac srcdir="${src.test}"
           destdir="${build.test}"
           includeantruntime="false"
           encoding="UTF-8">
        <classpath refid="test.compile.classpath" />
    </javac>
</target>
~~~

Target compile-test phụ thuộc compile, nên mã ứng dụng được biên dịch trước. Sau đó, javac biên dịch test với classpath có lớp ứng dụng và thư viện JUnit.

Nếu test sử dụng thư viện khác, hãy thêm các JAR đó vào Path phù hợp. Với dự án nhiều module, classpath cần chứa cả output của các module mà test tham chiếu.

## 5. Chạy một lớp test bằng nested element test

Task `<junit>` có thể chạy một lớp test cụ thể bằng nested element `<test>`.

~~~xml
<target name="test-one" depends="compile-test">
    <mkdir dir="${reports.dir}" />

    <junit fork="true"
           printsummary="yes"
           haltonfailure="yes">
        <classpath refid="test.runtime.classpath" />

        <formatter type="plain" usefile="false" />
        <formatter type="xml" />

        <test name="com.example.CalculatorJUnit4Test"
              todir="${reports.dir}" />
    </junit>
</target>
~~~

Trong ví dụ:

- `fork="true"` chạy test trong JVM riêng.
- `printsummary="yes"` in thống kê ngắn.
- `haltonfailure="yes"` làm build thất bại nếu có test thất bại hoặc lỗi.
- `classpath` cung cấp lớp ứng dụng, lớp test và thư viện cần thiết.
- Formatter plain hiển thị kết quả trên console vì `usefile="false"`.
- Formatter XML tạo báo cáo có thể được CI hoặc công cụ khác đọc.
- `test` chỉ định tên đầy đủ của lớp test.

Nếu muốn chạy JUnit 3, có thể thay tên lớp thành `com.example.CalculatorTest`. Cùng một task có thể chạy lớp JUnit 3 hoặc JUnit 4 miễn classpath và cấu trúc test phù hợp.

## 6. Chạy nhiều test bằng batchtest

Khi dự án có nhiều lớp test, khai báo từng `<test>` sẽ dài. Nested element `<batchtest>` cho phép Ant thu thập test từ một hoặc nhiều resource collection, thường là FileSet.

~~~xml
<target name="test-all" depends="compile-test">
    <mkdir dir="${reports.dir}" />

    <junit fork="true"
           printsummary="yes"
           haltonfailure="yes"
           haltonerror="yes">
        <classpath refid="test.runtime.classpath" />

        <formatter type="plain" usefile="false" />
        <formatter type="xml" />

        <batchtest todir="${reports.dir}">
            <fileset dir="${build.test}">
                <include name="**/*Test.class" />
                <exclude name="**/Abstract*Test.class" />
            </fileset>
        </batchtest>
    </junit>
</target>
~~~

Ant quét thư mục build.test, tìm các lớp khớp mẫu và chuyển chúng thành tên lớp test để chạy. Mẫu `**/*Test.class` thường phù hợp với quy ước đặt tên test.

Ví dụ, FileSet có thể tìm:

- `com/example/CalculatorTest.class`
- `com/example/CalculatorJUnit4Test.class`
- `com/example/service/OrderServiceTest.class`

Không nên đưa lớp tiện ích hoặc lớp abstract không phải test vào tập quét. Dùng include/exclude rõ ràng để tránh Ant cố chạy những lớp không có test.

### 6.1. Kết hợp test và batchtest

Một task `<junit>` có thể chứa cả nested element `<test>` và `<batchtest>`. Cách này hữu ích khi muốn chạy một số lớp đặc biệt riêng, đồng thời quét phần test còn lại.

Ví dụ:

~~~xml
<junit fork="true" printsummary="yes">
    <classpath refid="test.runtime.classpath" />
    <formatter type="plain" usefile="false" />

    <test name="com.example.SmokeTest" todir="${reports.dir}" />

    <batchtest todir="${reports.dir}">
        <fileset dir="${build.test}">
            <include name="**/*Test.class" />
            <exclude name="**/SmokeTest.class" />
        </fileset>
    </batchtest>
</junit>
~~~

Ở đây, SmokeTest được chạy riêng, còn batchtest chạy các lớp khác. Loại SmokeTest khỏi FileSet để tránh chạy hai lần.

## 7. Cấu hình formatter và báo cáo

Formatter quyết định cách kết quả test được trình bày. Ant có các formatter dựng sẵn:

| Formatter | Nội dung |
|---|---|
| plain | Báo cáo văn bản với thống kê và thông tin lỗi |
| brief | Chỉ hiển thị chi tiết cho các test thất bại |
| xml | Báo cáo XML phù hợp cho công cụ CI và xử lý tự động |
| failure | Thu thập các test thất bại để tạo lớp có thể chạy lại, từ Ant 1.8.0 |

Ví dụ dùng plain trên console và XML ra file:

~~~xml
<junit fork="true" printsummary="yes">
    <classpath refid="test.runtime.classpath" />

    <formatter type="plain" usefile="false" />
    <formatter type="xml" />

    <batchtest todir="${reports.dir}">
        <fileset dir="${build.test}">
            <include name="**/*Test.class" />
        </fileset>
    </batchtest>
</junit>
~~~

Nếu không đặt `usefile="false"`, formatter mặc định ghi kết quả ra file. Với XML formatter, Ant tạo báo cáo cho từng lớp test trong thư mục todir.

Một số thuộc tính hữu ích:

- `printsummary`: in thống kê ngắn cho từng testcase; có thể dùng `on`, `off` hoặc `withOutAndErr`.
- `showoutput`: gửi output từ test vào log của Ant ngoài việc chuyển cho formatter.
- `outputtoformatters`: quyết định output test có được gửi đến formatter hay không.
- `todir`: thư mục lưu báo cáo cho test hoặc batchtest.
- `outfile`: tên cơ sở của file kết quả cho một test cụ thể.

Nếu test in nhiều dữ liệu qua System.out hoặc System.err, cân nhắc `showoutput="true"`. Mặc định output của test chủ yếu được gửi cho formatter, không nhất thiết xuất hiện trực tiếp trên console.

## 8. Xử lý test failure và test error

JUnit phân biệt assertion thất bại với lỗi phát sinh trong quá trình chạy:

- **Failure:** một assertion không đúng, ví dụ kết quả thực tế khác kết quả mong đợi.
- **Error:** test gặp exception hoặc lỗi ngoài kết quả assertion, ví dụ lỗi khởi tạo đối tượng hoặc lỗi môi trường.

Task `<junit>` có các thuộc tính:

| Thuộc tính | Ý nghĩa | Mặc định |
|---|---|---|
| haltonfailure | Dừng build khi có test thất bại; error cũng được xem là failure | false |
| haltonerror | Dừng build khi có error trong test | false |
| failureproperty | Đặt property khi có failure; error cũng được tính | Không đặt |
| errorproperty | Đặt property khi có error | Không đặt |

Đối với CI, có thể cấu hình dừng ngay khi test lỗi:

~~~xml
<junit fork="true"
       haltonfailure="true"
       haltonerror="true"
       printsummary="yes">
    <classpath refid="test.runtime.classpath" />
    <formatter type="plain" usefile="false" />
    <batchtest todir="${reports.dir}">
        <fileset dir="${build.test}">
            <include name="**/*Test.class" />
        </fileset>
    </batchtest>
</junit>
~~~

Nếu muốn thực hiện thêm bước dọn dẹp hoặc thu thập log trước khi làm build thất bại, hãy không dừng ngay trong task. Thay vào đó, đặt failureproperty và errorproperty:

~~~xml
<junit fork="true"
       haltonfailure="false"
       haltonerror="false"
       failureproperty="tests.failed"
       errorproperty="tests.errored">
    <classpath refid="test.runtime.classpath" />
    <formatter type="plain" usefile="false" />
    <batchtest todir="${reports.dir}">
        <fileset dir="${build.test}">
            <include name="**/*Test.class" />
        </fileset>
    </batchtest>
</junit>

<!-- Có thể thực hiện các bước thu thập log hoặc cleanup ở đây. -->

<fail if="tests.failed"
      message="JUnit tests failed or produced errors." />
~~~

Property failureproperty được đặt khi có failure; error cũng được tính là failure. errorproperty giúp phân biệt trường hợp lỗi riêng. Vì property Ant có tính bất biến, nên dùng tên property mới cho mỗi lần chạy trong cùng một project nếu cần theo dõi kết quả độc lập.

## 9. Khi nào nên fork test?

Mặc định, `fork="false"`: test chạy trong JVM của Ant. Đặt `fork="true"` để chạy trong JVM riêng.

Fork hữu ích khi:

- Test hoặc thư viện test có thể gọi System.exit() hay Runtime.exit().
- Muốn cô lập static state hoặc thay đổi system property giữa các lần chạy.
- Cần đặt timeout hoặc giới hạn bộ nhớ cho JVM test.
- Muốn chọn JVM chạy test bằng thuộc tính jvm.
- Một test có thể gây treo hoặc làm hỏng JVM.

Ví dụ:

~~~xml
<junit fork="true"
       jvm="java"
       maxmemory="1024m"
       timeout="120000"
       printsummary="yes">
    <classpath refid="test.runtime.classpath" />
    <formatter type="plain" usefile="false" />
    <test name="com.example.SlowIntegrationTest"
          todir="${reports.dir}" />
</junit>
~~~

Trong ví dụ, JVM test có giới hạn heap tối đa 1 GB và timeout 120.000 ms. Timeout chỉ có tác dụng khi fork=true.

Thuộc tính `forkmode` điều khiển số JVM được tạo khi fork:

- `perTest`: tạo JVM riêng cho từng lớp test; đây là mặc định.
- `perBatch`: tạo JVM cho từng batchtest và một JVM cho các test khai báo riêng.
- `once`: cố gắng dùng một JVM cho tất cả test có cấu hình tương thích.

Dù chọn once, Ant vẫn có thể phải tạo nhiều JVM nếu các test có thiết lập khác nhau về error/failure handling hoặc filtertrace. Nếu dùng threads để chạy song song, test phải được fork với forkmode phù hợp; khả năng threads có từ Ant 1.9.4.

Fork có chi phí khởi động JVM. Với test nhanh và đơn giản, chạy trong JVM Ant có thể nhanh hơn; với test cần cô lập, timeout hoặc kiểm soát bộ nhớ, fork thường an toàn hơn.

## 10. Ví dụ hoàn chỉnh: biên dịch và chạy cả JUnit 3 lẫn JUnit 4

Buildfile sau minh họa một pipeline đơn giản:

~~~xml
<project name="calculator" default="test" basedir=".">
    <property name="src.main" location="src/main/java" />
    <property name="src.test" location="src/test/java" />
    <property name="build.main" location="build/classes" />
    <property name="build.test" location="build/test-classes" />
    <property name="reports.dir" location="build/reports/junit" />
    <property name="junit.jar" location="lib/junit-4.13.2.jar" />
    <property name="hamcrest.jar" location="lib/hamcrest-core-1.3.jar" />

    <path id="test.compile.classpath">
        <pathelement location="${build.main}" />
        <pathelement location="${junit.jar}" />
        <pathelement location="${hamcrest.jar}" />
    </path>

    <path id="test.runtime.classpath">
        <pathelement location="${build.main}" />
        <pathelement location="${build.test}" />
        <pathelement location="${junit.jar}" />
        <pathelement location="${hamcrest.jar}" />
    </path>

    <target name="clean">
        <delete dir="build" />
    </target>

    <target name="compile">
        <mkdir dir="${build.main}" />
        <javac srcdir="${src.main}"
               destdir="${build.main}"
               includeantruntime="false"
               encoding="UTF-8" />
    </target>

    <target name="compile-test" depends="compile">
        <mkdir dir="${build.test}" />
        <javac srcdir="${src.test}"
               destdir="${build.test}"
               includeantruntime="false"
               encoding="UTF-8">
            <classpath refid="test.compile.classpath" />
        </javac>
    </target>

    <target name="test" depends="compile-test">
        <mkdir dir="${reports.dir}" />

        <junit fork="true"
               printsummary="yes"
               haltonfailure="yes"
               haltonerror="yes">
            <classpath refid="test.runtime.classpath" />

            <formatter type="plain" usefile="false" />
            <formatter type="xml" />

            <batchtest todir="${reports.dir}">
                <fileset dir="${build.test}">
                    <include name="**/*Test.class" />
                    <exclude name="**/Abstract*Test.class" />
                </fileset>
            </batchtest>
        </junit>
    </target>
</project>
~~~

Trước khi chạy, bảo đảm:

- `ant-junit.jar` và JUnit JAR có thể được Ant nạp.
- JUnit và Hamcrest JAR đúng với phiên bản test được dùng.
- Mã ứng dụng đã biên dịch vào build/classes.
- Mã test được biên dịch vào build/test-classes.

Chạy toàn bộ quy trình:

~~~bash
ant clean test
~~~

Ant xóa output cũ, biên dịch ứng dụng, biên dịch test, rồi quét lớp test và chạy chúng. Kết quả văn bản hiển thị trên console; báo cáo XML được ghi vào build/reports/junit.

Nếu chỉ muốn chạy một lớp test, thay batchtest bằng:

~~~xml
<test name="com.example.CalculatorJUnit4Test"
      todir="${reports.dir}" />
~~~

## 11. JUnit 3/4 và JUnit 5

Task `<junit>` được thiết kế cho JUnit 3 và JUnit 4. Nó hỗ trợ các test JUnit 4 thuần dùng annotation, nhưng không phải runner cho JUnit Platform của JUnit 5.

Nếu dự án dùng JUnit 5 (Jupiter), hãy xem task `<junitlauncher>` của Ant, được bổ sung từ Ant 1.10.3. Không nên cố đưa JUnit 5 engine vào task `<junit>` và kỳ vọng task tự chạy các annotation `org.junit.jupiter.api.Test`.

Với dự án đang dùng JUnit 3 hoặc JUnit 4, task `<junit>` vẫn là cách tích hợp trực tiếp với Ant. Nếu đang chuyển sang JUnit 5, nên lập kế hoạch thay đổi runner và dependency riêng.

## 12. Những lỗi thường gặp

### 12.1. Ant không nhận diện task junit

Lỗi thường do `ant-junit.jar` chưa được thêm vào classpath của Ant. Đưa JAR vào ANT_HOME/lib, dùng -lib hoặc khai báo taskdef với classpath phù hợp.

### 12.2. Không tìm thấy junit.framework.TestCase hoặc org.junit.Test

Task đã được nạp nhưng JUnit JAR chưa có trong classpath phù hợp. Kiểm tra nested classpath của `<junit>` và classpath khi biên dịch test.

### 12.3. Test không được tìm thấy trong batchtest

Kiểm tra thư mục todir/Fileset thực tế, mẫu include và tên file .class. Batchtest phải quét output đã biên dịch, không phải một thư mục rỗng hoặc nhầm với thư mục mã nguồn.

### 12.4. Lớp test được tìm thấy nhưng báo lỗi NoClassDefFoundError

Classpath chạy test thiếu lớp ứng dụng hoặc thư viện mà test phụ thuộc. Hãy thêm output của ứng dụng và các JAR cần thiết vào test.runtime.classpath.

### 12.5. Test failure không làm build thất bại

Mặc định haltonfailure và haltonerror đều tắt. Đặt chúng thành true nếu muốn task dừng build ngay khi test lỗi; hoặc dùng failureproperty/errorproperty và task fail ở bước sau.

### 12.6. Output của test không xuất hiện trên console

Mặc định output được gửi cho formatter, không nhất thiết được ghi vào log Ant. Dùng formatter phù hợp, usefile="false" hoặc showoutput="true" nếu cần xem output trực tiếp.

### 12.7. Test gọi System.exit làm kết thúc Ant

Chạy test trong JVM riêng bằng fork="true" để việc gọi System.exit không kết thúc JVM điều phối build.

## 13. Thực hành tốt

- **Tách source và output test.** Dùng src/test/java và build/test-classes để không trộn mã test với artifact ứng dụng.
- **Quản lý dependency JUnit rõ ràng.** Cung cấp ant-junit.jar cho Ant và JUnit JAR cho test classpath.
- **Dùng tên lớp có quy ước.** Các tên như *Test giúp batchtest chọn lớp test dễ dàng.
- **Dùng test cho một lớp và batchtest cho nhiều lớp.** Chọn phạm vi phù hợp với mục đích chạy.
- **Tạo báo cáo XML trong CI.** Dùng formatter type="xml" và thư mục todir ổn định.
- **Bật haltonfailure cho pipeline cần kết quả nghiêm ngặt.** Nếu cần cleanup sau test, dùng failureproperty/errorproperty rồi fail ở bước cuối.
- **Fork khi cần cô lập.** Dùng fork cho System.exit, timeout, giới hạn heap hoặc môi trường test riêng.
- **Không quét mọi lớp trong output.** Dùng include/exclude để tránh chạy helper hoặc abstract test class.
- **Giữ classpath compile và runtime đồng bộ.** Test có thể biên dịch được nhưng vẫn lỗi khi chạy nếu thiếu dependency.
- **Dùng đúng runner theo thế hệ JUnit.** Task junit dành cho JUnit 3/4; JUnit 5 cần JUnit Platform runner như junitlauncher.

## 14. Kết luận

Task `<junit>` của Apache Ant chạy được cả test JUnit 3 kế thừa `TestCase` và test JUnit 4 dùng annotation `@Test`. Để sử dụng, Ant cần nạp được `ant-junit.jar`, test cần JUnit JAR trong classpath, và mã ứng dụng cùng mã test phải được biên dịch trước khi chạy.

Dùng nested element `<test>` để chạy một lớp, hoặc `<batchtest>` để quét nhiều lớp theo mẫu. Formatter tạo báo cáo văn bản hoặc XML; haltonfailure, haltonerror và các property tương ứng kiểm soát cách build phản ứng với kết quả. Chọn fork khi cần JVM riêng, timeout hoặc giới hạn bộ nhớ. Với JUnit 5, dùng task JUnit Platform phù hợp thay vì task junit truyền thống.

## Tài liệu tham khảo

- [Apache Ant JUnit Task](https://ant.apache.org/manual/Tasks/junit.html)
- [Apache Ant JUnitLauncher Task](https://ant.apache.org/manual/Tasks/junitlauncher.html)
- [JUnit 4.13.2 Documentation](https://junit.org/junit4/)
- [JUnit 4.13.2 API](https://junit.org/junit4/javadoc/4.13.2/)


# Tổng hợp báo cáo HTML bằng `junitreport` và định dạng XML tương thích

Khi chạy kiểm thử tự động bằng Apache Ant, kết quả từng test có thể được ghi thành các file XML. Những file này phù hợp cho công cụ CI đọc máy, nhưng khó xem nhanh khi cần biết test nào thành công, test nào thất bại và lỗi xảy ra ở đâu. Task `<junitreport>` tổng hợp các file kết quả XML của JUnit thành báo cáo HTML để nhóm phát triển xem trong trình duyệt.

Để tạo báo cáo, cần hiểu hai bước riêng biệt:

1. Task `<junit>` chạy test và ghi kết quả bằng XML formatter.
2. Task `<junitreport>` đọc các XML đó, tổng hợp test suite và tạo HTML.

`junitreport` không tự chạy test. Nếu không có file XML đầu vào đúng định dạng, task không thể tạo báo cáo có ý nghĩa.

## 1. Luồng tạo báo cáo

Một build kiểm thử thường có luồng như sau:

```text
Mã nguồn test đã biên dịch
          |
          v
      <junit>
          |
          | formatter type="xml"
          v
  XML cho từng test suite
          |
          v
    <junitreport>
          |
          +----> XML tổng hợp
          |
          v
    XSLT chuyển đổi
          |
          v
       Báo cáo HTML
```

Thư mục XML và thư mục HTML nên được tách riêng. XML là dữ liệu đầu vào để công cụ xử lý; HTML là sản phẩm dành cho người đọc. Khi cần chạy lại test, có thể xóa thư mục XML cũ để tránh đưa kết quả từ lần chạy trước vào báo cáo mới.

## 2. Tạo XML kết quả từ task `<junit>`

Task `<junit>` hỗ trợ formatter. Để ghi kết quả XML, khai báo `<formatter type="xml"/>`. Với `batchtest`, thuộc tính `todir` chỉ định thư mục lưu các file kết quả.

```xml
<project name="junit-report-example" default="test">
    <property name="test.src.dir" location="src/test"/>
    <property name="test.classes.dir" location="build/test-classes"/>
    <property name="main.classes.dir" location="build/classes"/>
    <property name="test.xml.dir" location="build/test-results"/>

    <target name="test">
        <!-- Loại kết quả cũ để report chỉ chứa lần chạy hiện tại. -->
        <delete dir="${test.xml.dir}"/>
        <mkdir dir="${test.xml.dir}"/>

        <junit fork="true"
               printsummary="yes"
               haltonfailure="no">
            <classpath>
                <pathelement location="${main.classes.dir}"/>
                <pathelement location="${test.classes.dir}"/>
                <pathelement location="lib/junit.jar"/>
            </classpath>

            <formatter type="xml"/>

            <batchtest todir="${test.xml.dir}">
                <fileset dir="${test.src.dir}">
                    <include name="**/*Test.java"/>
                </fileset>
            </batchtest>
        </junit>
    </target>
</project>
```

Các điểm cần chú ý:

- `formatter type="xml"` yêu cầu JUnit formatter ghi kết quả ở dạng XML.
- `batchtest` chạy một nhóm test được chọn bằng fileset. Ví dụ trên tìm các file nguồn có tên kết thúc bằng `Test.java`; class đã biên dịch tương ứng phải có mặt trên classpath.
- `todir` của `batchtest` là thư mục chứa kết quả XML. Với XML formatter mặc định, tên file thường có dạng `TEST-<tên-test-class>.xml`.
- `fork="true"` chạy test trong JVM riêng, giúp tách trạng thái test khỏi JVM của Ant.
- `haltonfailure="no"` cho phép target tiếp tục sau khi có test thất bại để báo cáo vẫn được tạo. Cần có bước kiểm soát kết quả sau khi report hoàn thành nếu build phải trả trạng thái thất bại.

Task JUnit là task tùy chọn của Ant. Môi trường chạy cần có phần hỗ trợ Ant JUnit và thư viện JUnit tương thích trong classpath phù hợp. Nếu Ant báo không nhận diện được task `junit`, hãy kiểm tra cài đặt task tùy chọn và classpath trước khi xem xét cấu hình test.

## 3. Tổng hợp XML và tạo HTML bằng `<junitreport>`

Sau khi `<junit>` tạo các file XML, dùng `<junitreport>` để đọc chúng. Fileset bên trong `junitreport` xác định các file đầu vào; phần tử `<report>` chỉ định định dạng và thư mục HTML.

```xml
<project name="junit-report-example"
         default="test-report">

    <property name="test.xml.dir" location="build/test-results"/>
    <property name="test.html.dir" location="build/reports/junit"/>

    <target name="test-report">
        <junitreport todir="${test.xml.dir}">
            <fileset dir="${test.xml.dir}">
                <include name="TEST-*.xml"/>
            </fileset>

            <report format="frames"
                    todir="${test.html.dir}"/>
        </junitreport>
    </target>
</project>
```

`junitreport` thực hiện hai công việc liên quan:

1. Đọc các file XML được chọn và tạo dữ liệu tổng hợp trong thư mục `todir` của task.
2. Dùng stylesheet XSLT để chuyển dữ liệu kết quả thành HTML trong `todir` của phần tử `<report>`.

Hai thuộc tính `todir` có vai trò khác nhau. `junitreport todir` là nơi task lưu dữ liệu XML tổng hợp; `report todir` là nơi lưu trang HTML và các tài nguyên báo cáo. Đừng đặt nhầm chúng vào cùng một ý nghĩa.

### Chọn dạng HTML

Thuộc tính `format` của `<report>` hỗ trợ hai dạng trình bày:

| Giá trị | Kết quả | Khi sử dụng |
|---|---|---|
| `frames` | Báo cáo chia khung điều hướng và nội dung | Khi muốn duyệt suite, package và test từ các khung riêng |
| `noframes` | Báo cáo HTML không dùng frames | Khi cần trang đơn giản hơn hoặc môi trường xem không thuận tiện với frames |

Ví dụ tạo báo cáo không dùng frames:

```xml
<junitreport todir="build/test-results">
    <fileset dir="build/test-results">
        <include name="TEST-*.xml"/>
    </fileset>
    <report format="noframes" todir="build/reports/junit"/>
</junitreport>
```

Nếu muốn thay đổi giao diện, có thể cung cấp thư mục stylesheet bằng thuộc tính `styledir` của `<report>`:

```xml
<report format="frames"
        todir="build/reports/junit"
        styledir="config/junit-xsl"/>
```

Thư mục stylesheet phải chứa các XSL mà kiểu báo cáo được chọn yêu cầu. Khi tự tùy chỉnh stylesheet, hãy bắt đầu từ stylesheet mặc định tương ứng với phiên bản Ant đang dùng và giữ nguyên cấu trúc XML mà stylesheet cần đọc.

## 4. Định dạng XML tương thích với JUnitReport

`junitreport` cần dữ liệu XML kết quả test theo cấu trúc mà bộ xử lý và stylesheet của Ant hiểu. Lựa chọn an toàn nhất là để task `<junit>` tạo file bằng `formatter type="xml"`; khi đó định dạng đầu ra được thiết kế để làm đầu vào cho `junitreport`.

Một file kết quả theo cấu trúc JUnit thường có phần tử gốc `<testsuite>`, các phần tử con `<testcase>` và thông tin lỗi trong `<failure>` hoặc `<error>`. Ví dụ rút gọn sau minh họa các thành phần quan trọng:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.example.CalculatorTest"
           tests="3"
           failures="1"
           errors="0"
           time="0.025">
    <properties>
        <property name="java.version" value="21"/>
    </properties>

    <testcase classname="com.example.CalculatorTest"
              name="addsTwoNumbers"
              time="0.003"/>

    <testcase classname="com.example.CalculatorTest"
              name="subtractsTwoNumbers"
              time="0.002"/>

    <testcase classname="com.example.CalculatorTest"
              name="rejectsInvalidInput"
              time="0.020">
        <failure message="Expected 4 but was 5"
                 type="java.lang.AssertionError">
            java.lang.AssertionError: Expected 4 but was 5
            at com.example.CalculatorTest.rejectsInvalidInput(CalculatorTest.java:42)
        </failure>
    </testcase>

    <system-out><![CDATA[Running CalculatorTest]]></system-out>
    <system-err><![CDATA[]]></system-err>
</testsuite>
```

Đây là ví dụ minh họa cấu trúc, không phải cam kết rằng mọi phiên bản test framework đều xuất XML giống hệt nhau. Các producer khác nhau có thể thêm hoặc bỏ thuộc tính, dùng phần tử gốc khác, hoặc biểu diễn trạng thái bỏ qua theo cách riêng. `junitreport` của Ant được thiết kế quanh XML do Ant JUnit formatter tạo ra; một file mang tên “JUnit XML” từ framework khác chưa chắc tương thích hoàn toàn.

### Ý nghĩa của các phần tử chính

| Thành phần | Vai trò |
|---|---|
| `testsuite` | Nhóm kết quả của một test class hoặc một suite; chứa thống kê tổng số test, failures, errors và thời gian |
| `testcase` | Một test method, thường có `classname`, `name` và `time` |
| `failure` | Test đã chạy nhưng assertion hoặc điều kiện mong đợi không đạt |
| `error` | Test gặp lỗi thực thi ngoài kết quả assertion thông thường, ví dụ exception không được xử lý |
| `properties` / `property` | Metadata môi trường hoặc cấu hình gắn với suite |
| `system-out` | Nội dung stdout được test ghi lại nếu formatter hỗ trợ |
| `system-err` | Nội dung stderr được test ghi lại nếu formatter hỗ trợ |

Số liệu `tests`, `failures`, `errors` và thời gian phải nhất quán với các testcase được ghi. Nội dung XML phải well-formed: thẻ mở/đóng đúng cặp, ký tự đặc biệt được escape và giá trị thuộc tính nằm trong dấu nháy. Nếu chứa ký tự `<` hoặc `&` trong nội dung thông thường, hãy dùng `&lt;` hoặc `&amp;`; với nội dung văn bản nhiều dòng, có thể dùng CDATA khi phù hợp.

### Vì sao một XML hợp lệ vẫn có thể không tạo được báo cáo đúng?

XML well-formed chỉ chứng minh tài liệu có cú pháp XML hợp lệ. Nó không chứng minh cấu trúc test result đúng với những gì stylesheet của `junitreport` mong đợi. Một file XML tùy chỉnh có thể parse được nhưng không có `testsuite`, `testcase`, `failure` theo vị trí hoặc tên mà Ant cần. Khi tích hợp framework khác, hãy so sánh output thực tế của nó với output do Ant JUnit formatter tạo ra, sau đó thử report bằng một bộ test nhỏ trước khi đưa vào pipeline chính.

## 5. Ghép các bước thành một target hoàn chỉnh

Ví dụ dưới đây chạy test, tạo HTML và vẫn đánh dấu build thất bại nếu test có lỗi. `failureproperty` và `errorproperty` cho phép giữ lại kết quả thất bại trong khi `haltonfailure="no"` để task không dừng trước bước tổng hợp báo cáo.

```xml
<project name="complete-junit-report" default="verify">
    <property name="test.src.dir" location="src/test"/>
    <property name="test.xml.dir" location="build/test-results"/>
    <property name="test.html.dir" location="build/reports/junit"/>

    <target name="verify">
        <delete dir="${test.xml.dir}"/>
        <delete dir="${test.html.dir}"/>
        <mkdir dir="${test.xml.dir}"/>

        <junit fork="true"
               printsummary="yes"
               haltonfailure="no"
               failureproperty="tests.failed"
               errorproperty="tests.errored">
            <classpath>
                <pathelement location="build/classes"/>
                <pathelement location="build/test-classes"/>
                <pathelement location="lib/junit.jar"/>
            </classpath>

            <formatter type="xml"/>

            <batchtest todir="${test.xml.dir}">
                <fileset dir="${test.src.dir}">
                    <include name="**/*Test.java"/>
                </fileset>
            </batchtest>
        </junit>

        <junitreport todir="${test.xml.dir}">
            <fileset dir="${test.xml.dir}">
                <include name="TEST-*.xml"/>
            </fileset>
            <report format="frames" todir="${test.html.dir}"/>
        </junitreport>

        <!-- Giữ báo cáo để có thể xem trước khi build trả trạng thái thất bại. -->
        <fail if="tests.failed" message="JUnit tests failed; see ${test.html.dir}"/>
        <fail if="tests.errored" message="JUnit tests had errors; see ${test.html.dir}"/>
    </target>
</project>
```

Thứ tự rất quan trọng: chạy test trước, tổng hợp XML sau, cuối cùng mới đánh dấu build thất bại. Nếu đặt `fail` ngay sau `<junit>`, target có thể dừng trước khi `<junitreport>` được thực thi. Trong một pipeline lớn hơn, có thể tách `test`, `test-report` và `verify` thành các target riêng, nhưng cần bảo đảm target tạo report luôn được gọi sau khi XML đã có.

Nếu `<junit>` không tạo ra XML nào — chẳng hạn fileset không tìm thấy test — fileset của `junitreport` cũng sẽ không có đầu vào. Hãy kiểm tra số lượng test được chọn và các file thực tế trong `test.xml.dir` trước khi kết luận lỗi nằm ở XSLT.

## 6. Tổ chức thư mục và quản lý kết quả cũ

Một cấu trúc thường dùng:

```text
build/
├── test-results/
│   ├── TEST-com.example.CalculatorTest.xml
│   └── TEST-com.example.UserServiceTest.xml
└── reports/
    └── junit/
        ├── index.html
        └── ... stylesheet assets ...
```

Giữ XML và HTML ở hai thư mục riêng giúp dễ xác định dữ liệu đầu vào và sản phẩm cuối. Có thể lưu XML làm artifact CI để một công cụ khác đọc lại, còn HTML để người phát triển tải xuống hoặc xem trực tiếp.

Trước mỗi lần chạy mới, nên xóa thư mục XML đầu vào hoặc dùng thư mục riêng theo build number. Nếu chỉ ghi đè những file có tên trùng, các file XML còn sót từ test đã bị xóa hoặc đổi tên vẫn có thể được fileset chọn và xuất hiện trong báo cáo. Xóa thư mục HTML trước khi report cũng tránh giữ lại trang hoặc tài nguyên không còn được tạo trong lần chạy mới.

Pattern của fileset phải khớp đúng file kết quả. Ví dụ `TEST-*.xml` phù hợp với tên do XML formatter của Ant thường tạo. Nếu dùng pattern rộng như `**/*.xml`, hãy bảo đảm thư mục không chứa XML cấu hình, XML tổng hợp cũ hoặc tài liệu không phải kết quả test.

## 7. Lỗi thường gặp và cách xử lý

1. **`junitreport` không tìm thấy file đầu vào.** Kiểm tra `<formatter type="xml"/>`, `todir` của batchtest, và pattern trong fileset. Mở thư mục kết quả để xác nhận có file `TEST-*.xml`.
2. **Task `<junit>` hoặc `<junitreport>` không được nhận diện.** Kiểm tra phần hỗ trợ Ant JUnit và classpath của Ant. Đảm bảo các JAR cần thiết đã được cài đặt ở nơi Ant nạp task tùy chọn.
3. **Báo cáo không có test hoặc thống kê bằng không.** Có thể fileset test không chọn đúng source/class, XML đầu vào rỗng hoặc XML không chứa cấu trúc suite/testcase mà report cần. Kiểm tra file XML đầu vào trước khi xem HTML.
4. **XML parse error.** Kiểm tra ký tự đặc biệt chưa escape, thẻ đóng thiếu, encoding và nội dung log được ghi trực tiếp vào XML. Nếu tạo XML thủ công, dùng XML writer thay vì nối chuỗi tùy tiện.
5. **Có test cũ trong báo cáo.** Xóa thư mục XML trước khi chạy test hoặc tạo một thư mục đầu ra duy nhất cho mỗi lần build. Thu hẹp fileset để chỉ lấy XML kết quả hiện tại.
6. **Test thất bại nên HTML không được tạo.** Kiểm tra `haltonfailure`. Nếu cần luôn tạo report, để JUnit task tiếp tục sau test failure, ghi nhận trạng thái bằng property rồi dùng `<fail>` sau bước `junitreport`.
7. **Báo cáo HTML không có giao diện mong muốn.** Kiểm tra `format` (`frames` hoặc `noframes`), thư mục `todir` và stylesheet. Nếu dùng `styledir`, bảo đảm thư mục có các XSL cần thiết cho kiểu báo cáo.
8. **XML từ framework khác không hiển thị đầy đủ.** “JUnit XML” là tên gọi chung cho nhiều biến thể output. So sánh cấu trúc thực tế với file do Ant XML formatter tạo, đặc biệt phần tử gốc, `testsuite`, `testcase`, `failure` và `error`.
9. **Build báo thành công dù test có lỗi.** Nếu đặt `haltonfailure="no"` chỉ để tạo report, hãy thêm cơ chế kiểm tra sau report như `failureproperty`/`errorproperty` và `<fail>`. Việc tạo HTML thành công không có nghĩa test đã pass.

## 8. Quy trình sử dụng trong CI

Để có kết quả dễ kiểm tra và ổn định giữa các lần build:

1. Biên dịch test và chuẩn bị classpath gồm code ứng dụng, test classes và JUnit.
2. Xóa hoặc tạo mới thư mục XML kết quả cho lần chạy hiện tại.
3. Chạy `<junit>` với XML formatter và chọn test bằng fileset rõ ràng.
4. Xác nhận XML đầu vào đã được tạo; dùng pattern chỉ khớp các file kết quả.
5. Chạy `<junitreport>` để tạo HTML và XML tổng hợp.
6. Lưu thư mục HTML làm artifact cho người đọc; lưu XML nếu CI hoặc công cụ khác cần xử lý máy.
7. Sau khi report đã tạo, đánh dấu build thất bại nếu có test failure hoặc error.

## Tài liệu tham khảo

- [Apache Ant Manual — JUnit Task](https://ant.apache.org/manual/Tasks/junit.html): chạy test, batchtest, formatter XML và các thuộc tính kiểm soát kết quả.
- [Apache Ant Manual — JUnitReport Task](https://ant.apache.org/manual/Tasks/junitreport.html): tổng hợp XML result files và tạo báo cáo HTML bằng XSLT.
- [Apache Ant Manual — FileSet](https://ant.apache.org/manual/Types/fileset.html): chọn file XML đầu vào bằng include/exclude pattern.

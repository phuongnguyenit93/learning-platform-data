# Phân biệt lỗi công cụ con, lỗi kiểm thử và lỗi gói phân phối trong Apache Ant

Khi chạy một bản build bằng **Apache Ant**, dòng `BUILD FAILED` chỉ cho biết Ant đã dừng do một lỗi. Dòng này không tự cho biết lỗi xuất phát từ **công cụ con**, **kiểm thử** hay **gói phân phối**. Muốn xử lý đúng, cần xác định task đang thực hiện, thông tin lỗi đầu tiên có ý nghĩa, mã thoát của tiến trình (nếu có) và trạng thái của các sản phẩm trung gian.

Bài học nằm trong chủ đề **Nhật ký và lỗi** của **Build Tool Ant**, tập trung vào cách nhận diện ba nhóm lỗi thường gặp, phân biệt triệu chứng với nguyên nhân gốc, tổ chức target để lỗi không bị che khuất, và đọc log để chọn hướng sửa thích hợp.

## 1. Ba nhóm lỗi có gì khác nhau?

| Nhóm lỗi | Đối tượng gặp vấn đề | Tín hiệu tiêu biểu | Câu hỏi cần trả lời trước tiên |
|---|---|---|---|
| **Lỗi công cụ con** (*child tool failure*) | Chương trình được Ant gọi: `java`, `javac`, `git`, trình tạo mã, trình phân tích tĩnh, script hệ thống… | Không khởi chạy được chương trình; tiến trình trả mã thoát khác `0`; thông báo từ `<exec>`, `<java>` hoặc task bao bọc công cụ | Công cụ nào được gọi, với tham số và môi trường nào; nó đã chạy hay chưa? |
| **Lỗi kiểm thử** (*test failure/test error*) | Trường hợp kiểm thử hoặc môi trường chạy kiểm thử | Assertion thất bại, ngoại lệ trong test, timeout, lỗi khởi tạo bộ kiểm thử, báo cáo JUnit có `failures`/`errors` | Test nào thất bại? Do hành vi phần mềm sai hay do không chạy được test? |
| **Lỗi gói phân phối** (*packaging/distribution failure*) | Việc tạo hoặc xác thực đầu ra để phát hành: JAR, ZIP, WAR, manifest, tài nguyên, chữ ký số… | Task `<jar>`/`<zip>`/`<war>` thất bại; thiếu tệp đầu vào; không ghi được artifact; artifact tạo xong nhưng thiếu nội dung | Đầu vào đóng gói có đầy đủ không? Artifact có đúng cấu trúc, metadata và cách chạy mong đợi không? |

Một lỗi có thể mang **hai nhãn**: *giai đoạn* và *nguyên nhân*. Ví dụ, một script ký JAR được gọi ở giai đoạn `package` nhưng trả mã thoát `1`. Giai đoạn bị lỗi là **đóng gói**, còn cơ chế lỗi trực tiếp là **công cụ con trả mã thất bại**. Tương tự, test runner không thể khởi động do thiếu thư viện là lỗi trong giai đoạn kiểm thử, nhưng nguyên nhân nằm ở môi trường hoặc công cụ chạy test, chưa phải lỗi logic trong code được kiểm thử.

### Minh họa chuỗi build

~~~text
prepare
   |
   v
compile ------> tool-check ------> test ------> package
  |                 |               |              |
  |                 |               |              +-- Tao JAR/ZIP/WAR, manifest
  |                 |               +----------------- Chay test, doc report
  |                 +--------------------------------- Chay CLI, script, tool
  +--------------------------------------------------- Bien dich nguon

Neu mot giai doan THAT BAI va Ant dung build:
cac giai doan phu thuoc phia sau khong duoc chay.
~~~

Điều cần truy tìm là **sự kiện thất bại đầu tiên**, không phải thông báo thất bại cuối cùng. Khi `compile` lỗi, `package` có thể bị bỏ qua. Nếu cố chạy `package` riêng và thấy thiếu file `.class`, sự thiếu file đó có thể chỉ là hậu quả của lỗi biên dịch trước đó.

## 2. Cách đọc thông báo `BUILD FAILED`

Giả sử cuối terminal xuất hiện:

~~~text
BUILD FAILED
.../build.xml:42: External command failed with exit code 2
~~~

Hãy đọc ngược từ chỗ Ant báo lỗi để tìm:

1. **Target** nào đang chạy, ví dụ `tool-check`, `unit-test` hay `package`.
2. **Task** nào phát sinh lỗi, ví dụ `<exec>`, `<junit>`, `<jar>` hoặc `<fail>`.
3. **Thông báo cụ thể** từ công cụ hoặc báo cáo: đường dẫn thiếu, tên test, tên class, exit code, stack trace.
4. **Điều kiện kích hoạt**: thay đổi mã nguồn, phiên bản JDK, classpath, quyền ghi, tham số CLI, file manifest…
5. **Bằng chứng độc lập**: tệp log, báo cáo kiểm thử, danh sách file trong artifact, timestamp của file đầu ra.

Một lỗi được phát ra bởi `<fail>` đôi khi chỉ là **cổng kiểm tra** do người viết build đặt ra. Ví dụ, `<fail if="tool.failed"/>` báo lỗi ở dòng chứa task `fail`, nhưng nguyên nhân thực nằm ở tiến trình chạy trước đó. Vì vậy không nên chỉ nhìn tên task cuối cùng để phân loại.

Để có log tổng thể, chạy:

~~~bash
ant -verbose -logfile build.log build
~~~

`-verbose` giúp in thêm thông tin của Ant; `-logfile` đưa log của lệnh vào tệp. Nếu dự án có các task `<record>` riêng cho từng giai đoạn, có thể đối chiếu `build.log` với log của target đang lỗi. Không nên kết luận rằng một giai đoạn đã thành công chỉ vì tệp log của giai đoạn đó tồn tại: nó có thể là tệp còn lại từ lần build trước.

## 3. Lỗi công cụ con: khởi chạy, mã thoát và đầu ra

Ant có thể thực hiện tác vụ bằng chương trình bên ngoài qua `<exec>` hoặc tiến trình Java qua `<java fork="true">`. Với nhóm lỗi này, phân biệt ít nhất ba tình huống:

| Tình huống | Ví dụ | Ý nghĩa |
|---|---|---|
| **Không khởi chạy được** | Sai đường dẫn executable; thiếu quyền thực thi; không tìm thấy công cụ trong `PATH` | Chương trình chưa thực thi thành công; chưa thể suy luận lỗi từ logic của chương trình đó. |
| **Đã chạy, trả mã thoát khác 0** | Một CLI trả `2` do tham số không hợp lệ; script trả `1` vì thiếu file | Công cụ báo không thành công theo quy ước mã thoát của chính nó. |
| **Có thông báo đáng chú ý nhưng mã thoát 0** | Chương trình in cảnh báo ra `stderr` rồi kết thúc với `0` | Chưa đủ cơ sở kết luận lỗi; cần đọc tài liệu và quy ước của công cụ. |

### Ví dụ `<exec>` ghi log và kiểm tra mã thoát

Đoạn sau **cố ý truyền tùy chọn không hợp lệ** cho `java` để tạo lỗi công cụ con. Máy cần có lệnh `java` trong `PATH`:

~~~xml
<target name="tool-check">
    <mkdir dir="logs"/>

    <exec executable="java"
          failonerror="false"
          failifexecutionfails="true"
          resultproperty="tool.exit"
          output="logs/tool.stdout.log"
          error="logs/tool.stderr.log">
        <arg value="-unknown-option-for-demo"/>
    </exec>

    <condition property="tool.failed">
        <not>
            <equals arg1="${tool.exit}" arg2="0"/>
        </not>
    </condition>

    <fail if="tool.failed"
          message="TOOL FAILURE: java thoat voi ma ${tool.exit}; xem logs/tool.stderr.log"/>
</target>
~~~

Cách đọc:

- `executable="java"` là chương trình Ant gọi; phần `<arg>` là tham số truyền cho chương trình.
- `resultproperty="tool.exit"` nhận mã thoát khi tiến trình đã thực thi và kết thúc.
- `failonerror="false"` cho phép Ant xử lý mã thoát bằng `<condition>` và `<fail>`. Nếu chỉ đặt `false` rồi bỏ qua mã thoát, bản build có thể báo thành công dù công cụ đã lỗi.
- `failifexecutionfails="true"` giữ hành vi thất bại ngay nếu Ant không thể khởi chạy chương trình. Đây là trường hợp khác với chương trình đã chạy rồi trả mã khác `0`.
- `output` và `error` tách đầu ra chuẩn và thông báo lỗi chuẩn thành tệp để dễ điều tra. Không phải mọi công cụ đều dùng hai luồng này theo cùng một quy ước.

Khi chỉ muốn Ant dừng ngay nếu tiến trình trả mã thất bại, có thể dùng:

~~~xml
<exec executable="java" failonerror="true">
    <arg value="-unknown-option-for-demo"/>
</exec>
~~~

Đây là cách ngắn hơn nhưng khó tùy biến thông báo hoặc phân loại exit code theo quy ước riêng. Mã thoát **khác 0** thường là bằng chứng tốt hơn việc chỉ tìm từ `ERROR` trong log; tuy nhiên ý nghĩa cụ thể của mã `1`, `2`, `127`… phụ thuộc vào công cụ và hệ điều hành.

### Với chương trình Java do Ant khởi chạy

~~~xml
<java classname="demo.Checker"
      fork="true"
      failonerror="false"
      resultproperty="checker.exit">
    <classpath>
        <pathelement location="build/classes"/>
    </classpath>
</java>
~~~

Khi dùng `fork="true"`, ứng dụng chạy trong tiến trình JVM riêng và Ant có thể lấy mã thoát qua `resultproperty`. Nếu ứng dụng tự kết thúc bằng `System.exit(3)`, đó là mã thoát của ứng dụng. Ngược lại, stack trace do lỗi không tìm thấy main class hoặc sai classpath cho biết cần kiểm tra cách khởi chạy trước khi sửa chức năng nghiệp vụ.

**Trường hợp dễ nhầm:** `<javac>` cũng có thể gọi compiler, nhưng Ant thường hiển thị trực tiếp lỗi biên dịch qua task `javac`. Về mặt xử lý, hãy coi lỗi cú pháp, type hoặc classpath trong biên dịch là **lỗi giai đoạn compile**. Đừng gắn nhãn lỗi kiểm thử chỉ vì test chưa chạy được.

## 4. Lỗi kiểm thử: test thất bại hay test không chạy được?

Trong một lần chạy test, có ba kết quả đáng phân biệt:

- **Test pass:** các assertion và kiểm tra dự kiến thành công.
- **Test failure:** một assertion không đúng, chẳng hạn hàm trả `3` trong khi test mong đợi `2`.
- **Test error hoặc infrastructure error:** test ném ngoại lệ ngoài kiểm tra mong đợi, lỗi khởi tạo fixture, thiếu dependency, lỗi kết nối dịch vụ, không chạy được JVM test…

Báo cáo dạng JUnit XML thường có các số liệu như `tests`, `failures`, `errors` và `skipped`. Một báo cáo có `failures="1"` với tên case cụ thể khác với tình huống test runner không khởi động nên không tạo báo cáo nào.

### Ví dụ sử dụng `<junit>`

Giả sử dự án đã có class `demo.CalculatorTest`, class đã biên dịch và một path `test.classpath` chứa các thư viện cần thiết. Ant cần các thư viện hỗ trợ JUnit phù hợp với phiên bản đang dùng. Đoạn dưới là **mẫu tích hợp** vào build có cấu hình test sẵn:

~~~xml
<target name="unit-test" depends="compile">
    <mkdir dir="build/reports/tests"/>

    <junit printsummary="yes"
           fork="true"
           haltonfailure="false"
           haltonerror="false"
           failureproperty="test.assertion.failed"
           errorproperty="test.execution.error">

        <classpath>
            <pathelement location="build/classes"/>
            <path refid="test.classpath"/>
        </classpath>

        <formatter type="xml"/>
        <test name="demo.CalculatorTest" todir="build/reports/tests"/>
    </junit>

    <fail if="test.execution.error"
          message="TEST ERROR: khong thuc thi duoc mot hoac nhieu test; xem build/reports/tests"/>

    <fail if="test.assertion.failed"
          message="TEST FAILURE: assertion that bai; xem build/reports/tests"/>
</target>
~~~

Ở đây:

- `haltonfailure="false"` và `haltonerror="false"` để task có cơ hội ghi báo cáo và đặt các thuộc tính kết quả.
- `failureproperty` biểu thị nhóm test thất bại theo assertion; `errorproperty` biểu thị nhóm test error do JUnit phân loại.
- Hai lệnh `<fail>` ở cuối biến kết quả không thành công thành **lỗi build rõ ràng**. Nếu không cấu hình cơ chế dừng tương đương, pipeline có thể đi tiếp dù test lỗi.
- Nếu chính task JUnit không khởi tạo được do thiếu thư viện hỗ trợ hoặc cấu hình sai, Ant có thể ném lỗi trước khi các thuộc tính kết quả được đặt. Trường hợp đó cần đọc lỗi task và kiểm tra `classpath` hoặc test runner.

Các phiên bản JUnit khác nhau dùng cơ chế tích hợp phù hợp: cấu hình `<junit>` truyền thống dành cho các test được task này hỗ trợ; với JUnit Platform/JUnit 5, dự án có thể dùng `<junitlauncher>` hoặc runner khác. Dù dùng cách nào, nguyên tắc vẫn giống nhau: **ghi nhận kết quả test và bảo đảm build không âm thầm bỏ qua failure**.

### Đọc một báo cáo kiểm thử

Ví dụ thông tin rút gọn từ một báo cáo:

~~~xml
<testsuite name="demo.CalculatorTest"
           tests="3" failures="1" errors="0" skipped="0">
    <testcase name="addsTwoNumbers" classname="demo.CalculatorTest">
        <failure message="expected: 4 but was: 5"/>
    </testcase>
</testsuite>
~~~

Đây là **test failure**: runner đã chạy test, một kiểm tra cho kết quả không đúng. Hướng xử lý là tái hiện đầu vào của case `addsTwoNumbers`, kiểm tra mong đợi của test và logic của hàm được kiểm thử.

Nếu thay vào đó báo cáo có `errors="1"` kèm `ClassNotFoundException`, `NoClassDefFoundError` hay lỗi khởi tạo môi trường, cần xem xét đường dẫn class, dependencies, cấu hình fixture và điều kiện thực thi. Không nên tự động kết luận rằng hàm tính toán sai.

**Lưu ý:** Chỉ nhìn mã thoát tiến trình test có thể chưa đủ, nhất là khi runner được cấu hình không dừng trên lỗi. Đồng thời, số test chạy bằng `0` có thể khiến một pipeline trông như “xanh” dù bộ test không được phát hiện. Hãy xem số lượng test trong báo cáo và đặt chính sách tối thiểu theo yêu cầu của dự án.

## 5. Lỗi gói phân phối: tạo file được chưa chắc phát hành được

Giai đoạn packaging biến các sản phẩm biên dịch và tài nguyên thành dạng phát hành, chẳng hạn:

- `.jar` cho ứng dụng hoặc thư viện Java;
- `.war` cho ứng dụng web;
- `.zip` hoặc `.tar` cho bản phân phối gồm script, cấu hình, tài liệu và thư viện;
- gói đã ký số hoặc đã bổ sung metadata phát hành.

Nhóm lỗi này có hai lớp:

| Lớp | Biểu hiện | Ví dụ |
|---|---|---|
| **Task đóng gói thất bại trực tiếp** | Ant không thể tạo artifact | `basedir` không tồn tại; thư mục đích không ghi được; file bị khóa; ổ đĩa hết chỗ; manifest không hợp lệ. |
| **Artifact có tạo nhưng chưa đúng yêu cầu** | Build có thể báo thành công, nhưng gói không dùng được | Thiếu class, resource, thư viện; sai `Main-Class`; cấu trúc ZIP không đúng; script thiếu quyền thực thi; file quá cũ do dùng nhầm đầu ra. |

### Ví dụ đóng gói JAR và kiểm tra tồn tại

~~~xml
<target name="package" depends="unit-test">
    <property name="classes.dir" location="build/classes"/>
    <property name="dist.dir" location="build/dist"/>

    <available file="${classes.dir}"
               type="dir"
               property="package.inputs.present"/>
    <fail unless="package.inputs.present"
          message="PACKAGE INPUT ERROR: chua co thu muc class ${classes.dir}"/>

    <mkdir dir="${dist.dir}"/>

    <jar destfile="${dist.dir}/app.jar"
         basedir="${classes.dir}"
         whenempty="fail">
        <manifest>
            <attribute name="Main-Class" value="demo.Main"/>
        </manifest>
    </jar>

    <available file="${dist.dir}/app.jar"
               type="file"
               property="package.artifact.exists"/>
    <fail unless="package.artifact.exists"
          message="PACKAGE ERROR: khong tim thay app.jar"/>
</target>
~~~

Mẫu này giả định target `compile` và `unit-test` đã tồn tại và gói có class `demo.Main` phù hợp. Các `<available>` cùng `<fail>` tạo thông báo rõ hơn khi thiếu đầu vào hoặc đầu ra. `whenempty="fail"` giúp tránh tạo gói rỗng khi không có tài nguyên phù hợp. Các thuộc tính kết quả kiểm tra trong Ant thường được đặt một lần trong một lần chạy, nên dùng tên riêng để tránh tái sử dụng trạng thái cũ ngoài ý muốn.

Điều kiện `app.jar` **tồn tại** mới là kiểm tra đầu tiên. Nó không chứng minh trong JAR đã có đúng class, tài nguyên hoặc manifest. Sau bước đóng gói, có thể kiểm tra thủ công bằng JDK:

~~~bash
jar tf build/dist/app.jar
java -jar build/dist/app.jar
~~~

`jar tf` liệt kê nội dung lưu trong JAR. `java -jar` là một phép thử chạy thực tế chỉ phù hợp với **JAR có điểm vào thực thi**; JAR thư viện không nhất thiết phải chạy theo cách này. Với WAR hoặc ZIP, kiểm tra cấu trúc, các thư viện/tài nguyên bắt buộc và quy tắc triển khai tương ứng.

### Lỗi đóng gói có thể là hậu quả của giai đoạn trước

Xét tình huống:

~~~text
compile: KHONG thanh cong -> khong co build/classes/demo/Main.class
package: duoc goi thu cong -> JAR thieu Main.class
java -jar: Could not find or load main class ...
~~~

Thông báo ở bước chạy JAR phản ánh gói bị thiếu class, nhưng **nguyên nhân gốc** có thể là compile chưa hoàn thành. Cách sửa đúng là tìm lý do compile không sinh ra file, rồi build lại từ đầu. Chỉnh manifest sẽ không khắc phục được class chưa tồn tại.

Ngược lại, nếu `build/classes/demo/Main.class` có đủ nhưng manifest trỏ đến `demo.Start`, nguyên nhân thuộc về **cấu hình đóng gói**.

## 6. Bảng phân loại nhanh theo triệu chứng

| Triệu chứng quan sát | Chẩn đoán bước đầu | Bằng chứng cần tìm | Hành động hợp lý |
|---|---|---|---|
| `Cannot run program ...` hoặc `CreateProcess error` | Công cụ con không khởi chạy được | Giá trị `executable`, `PATH`, quyền, hệ điều hành | Xác nhận đường dẫn và môi trường chạy. |
| `exec returned: 2` hoặc `Result: 2` | Công cụ con đã chạy rồi thất bại | Exit code, stdout/stderr, tham số CLI | Đọc thông điệp của công cụ và quy ước exit code. |
| `expected: ... but was: ...` | Test assertion thất bại | Tên testcase, input, assertion, báo cáo JUnit | Tái hiện case và kiểm tra logic/mong đợi. |
| `NoClassDefFoundError` khi chạy test | Lỗi thực thi test hoặc dependency | Classpath, thư viện, test runner | Sửa dependency và môi trường test trước. |
| `Tests run: 0` trong khi mong đợi có test | Khả năng không phát hiện test | Tên class, filter, runner, thư mục biên dịch | Sửa cấu hình phát hiện và thêm điều kiện bắt buộc có test. |
| `basedir ... does not exist` ở task `jar` | Đầu vào packaging không có | Đường dẫn thư mục, kết quả compile | Xác định vì sao đầu vào chưa được tạo. |
| `Unable to create jar ...` | Lỗi ghi đầu ra đóng gói | Quyền ghi, path, dung lượng, file lock | Sửa điều kiện tạo artifact. |
| `no main manifest attribute` khi chạy JAR | Artifact thiếu metadata thực thi | `META-INF/MANIFEST.MF` | Cấu hình `Main-Class` nếu đây là JAR chạy trực tiếp. |
| JAR tồn tại nhưng thiếu file cấu hình | Artifact sai nội dung | `jar tf`, `fileset`, `zipfileset`, quy tắc include/exclude | Sửa lựa chọn file đưa vào gói. |

Bảng này dùng để khoanh vùng, **không thay thế việc đọc log**. Ví dụ, `ClassNotFoundException` có thể xảy ra trong test, chạy công cụ con hoặc khi chạy bản phân phối; ngữ cảnh quyết định giai đoạn đang lỗi.

## 7. Tổ chức target để giữ đúng ranh giới lỗi

Một lỗi rất khó truy tìm khi toàn bộ tác vụ bị nhét trong một target dài. Nên chia target theo trách nhiệm và tạo quan hệ phụ thuộc rõ ràng:

~~~xml
<project name="sample-build" default="build" basedir=".">

    <target name="prepare">
        <mkdir dir="build/classes"/>
        <mkdir dir="build/reports"/>
        <mkdir dir="build/dist"/>
    </target>

    <target name="compile" depends="prepare">
        <javac srcdir="src"
               destdir="build/classes"
               includeantruntime="false"/>
    </target>

    <!-- Chen quy trinh chay cong cu con va kiem tra exit code. -->
    <target name="tool-check" depends="compile">
        <echo message="[TOOL] Bat dau"/>
        <!-- <exec .../> va dieu kien <fail .../> o day -->
        <echo message="[TOOL] Hoan tat"/>
    </target>

    <!-- Chen task JUnit va dieu kien chan khi test loi. -->
    <target name="unit-test" depends="tool-check">
        <echo message="[TEST] Bat dau"/>
        <!-- <junit .../> va dieu kien <fail .../> o day -->
        <echo message="[TEST] Hoan tat"/>
    </target>

    <!-- Chen task jar/zip/war va kiem tra artifact. -->
    <target name="package" depends="unit-test">
        <echo message="[PACKAGE] Bat dau"/>
        <!-- <jar .../> va dieu kien xac thuc goi o day -->
        <echo message="[PACKAGE] Hoan tat"/>
    </target>

    <target name="build" depends="package"/>

</project>
~~~

Đây là **khung minh họa**, cần thay comment bằng các task thật trước khi sử dụng. Nhờ các `depends`, Ant chỉ đi đến `package` khi các giai đoạn trước đã hoàn tất mà không phát sinh lỗi dừng build.

Một số nguyên tắc khi thiết kế:

1. **Đặt thông điệp nhận diện ở đầu giai đoạn:** marker `[TOOL]`, `[TEST]`, `[PACKAGE]` giúp tìm nhanh log liên quan.
2. **Kiểm tra kết quả thực sự:** với `exec`, kiểm tra mã thoát; với test, kiểm tra failure/error; với package, kiểm tra cả việc tạo và tính hợp lệ của artifact.
3. **Không nuốt lỗi:** các cấu hình như `failonerror="false"` hoặc `haltonfailure="false"` chỉ an toàn nếu đi kèm điều kiện chuyển lỗi thành trạng thái build thất bại.
4. **Không dùng tên property lỗi giống nhau cho nhiều lệnh:** Ant thường coi property đã đặt là bất biến; đặt tên theo giai đoạn để tránh đánh dấu nhầm kết quả.
5. **Không sử dụng artifact cũ làm bằng chứng:** nếu một target không chạy, file còn trên đĩa từ lần build trước vẫn có thể xuất hiện. Dùng thư mục đầu ra sạch hoặc tách artifact theo lần chạy khi phù hợp.

## 8. Thực hành tái hiện ba kiểu lỗi

Để thấy khác biệt trong thông điệp mà **không cần cài JUnit**, có thể thử file `build.xml` độc lập dưới đây. Target `test-failure-demo` dùng `<fail>` để **mô phỏng** một assertion lỗi, nên nó không thay thế cho bộ kiểm thử JUnit thực tế.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-error-lab" default="help" basedir=".">

    <target name="help">
        <echo message="Chay: ant child-tool-failure"/>
        <echo message="Hoac: ant test-failure-demo"/>
        <echo message="Hoac: ant package-failure"/>
    </target>

    <target name="child-tool-failure">
        <mkdir dir="logs"/>

        <exec executable="java"
              failonerror="false"
              resultproperty="demo.tool.exit"
              error="logs/tool-error.log">
            <arg value="-invalid-option-for-lab"/>
        </exec>

        <condition property="demo.tool.failed">
            <not>
                <equals arg1="${demo.tool.exit}" arg2="0"/>
            </not>
        </condition>

        <fail if="demo.tool.failed"
              message="TOOL FAILURE: exit=${demo.tool.exit}; xem logs/tool-error.log"/>
    </target>

    <target name="test-failure-demo">
        <echo message="[TEST] assert: expected=2, actual=3"/>
        <fail message="TEST FAILURE (mo phong): assertion khong dat"/>
    </target>

    <target name="package-failure">
        <mkdir dir="build/dist"/>

        <!-- Co y chi den thu muc chua ton tai. -->
        <jar destfile="build/dist/demo.jar"
             basedir="build/classes-does-not-exist"/>
    </target>

</project>
~~~

Từ thư mục chứa file trên, chạy từng lệnh **riêng biệt**:

~~~bash
ant child-tool-failure
ant test-failure-demo
ant package-failure
~~~

Mỗi lệnh được thiết kế để thất bại theo một cách khác nhau:

| Lệnh | Nguồn lỗi chủ đạo | Bạn nên thấy |
|---|---|---|
| `ant child-tool-failure` | Công cụ `java` nhận tham số sai và trả exit code khác 0 | Thông báo từ `<fail>` kèm mã thoát và tệp `logs/tool-error.log`, giả sử Java có trong `PATH`. |
| `ant test-failure-demo` | Mô phỏng test assertion không đạt | Marker `[TEST]` và thông báo `TEST FAILURE (mo phong)`. |
| `ant package-failure` | Task `jar` nhận `basedir` không tồn tại | Thông báo về thư mục đầu vào packaging bị thiếu. |

Bài thực hành này cho thấy cùng một dòng `BUILD FAILED` có thể kết thúc ba chuỗi bằng chứng rất khác nhau. Khi chuyển sang dự án thật, thay lỗi mô phỏng bằng test chạy qua JUnit và kiểm tra báo cáo của nó.

## 9. Quy trình xử lý khi pipeline nhiều giai đoạn thất bại

### Bước 1: Xác định giai đoạn cuối đã bắt đầu

Tìm marker, tên target trong log hoặc thời điểm tạo báo cáo. Nếu dừng ở `unit-test`, chưa nên phân tích JAR cuối cùng. Nếu dừng ở `package`, xác nhận compile và test vừa chạy thành công trong **cùng lần build**, thay vì dựa vào file cũ.

### Bước 2: Tìm tín hiệu được phát ra gần nguồn nhất

- Với **công cụ con**: bắt đầu từ command line, executable, exit code và stderr/stdout.
- Với **kiểm thử**: bắt đầu từ tên testcase, assertion hoặc ngoại lệ đầu tiên; xem số test chạy và báo cáo.
- Với **đóng gói**: bắt đầu từ đường dẫn input/output, task `jar`/`zip`, manifest và danh sách nội dung artifact.

### Bước 3: Kiểm tra lỗi gốc hay lỗi lan truyền

Nếu `package` thiếu class, xác nhận compile có sinh class. Nếu test không tải được thư viện, kiểm tra bước chuẩn bị dependency. Nếu script ký số thất bại, phân biệt lệnh bị gọi sai với bản thân file gói không hợp lệ.

### Bước 4: Sửa tại đúng giai đoạn và chạy lại chuỗi phụ thuộc

Sửa classpath của test tại cấu hình test, sửa manifest tại target package, sửa tham số bên ngoài tại target exec. Sau đó chạy lại những bước phụ thuộc cần thiết để chắc chắn artifact cuối cùng lấy từ đầu ra mới.

### Bước 5: Giữ log và artifact đúng phiên để đối chiếu

Trên CI, có thể lưu log riêng theo job/build number và báo cáo test XML. Với artifact phát hành, nên có nhãn phiên bản hoặc checksum để xác nhận đang kiểm tra đúng file. Các thông tin này giúp phân biệt lỗi tái hiện được với lỗi môi trường theo từng lần chạy.

## 10. Những nhầm lẫn thường gặp

**“Cứ thấy stderr là công cụ con thất bại.”** Không hẳn. Một số công cụ đưa warning hoặc output trạng thái ra stderr nhưng trả exit code `0`. Cần xét quy ước của công cụ.

**“Build báo thành công nghĩa là test đã pass.”** Chưa chắc. Nếu task kiểm thử không dừng build trên failure hoặc không tìm được test nào, Ant vẫn có thể đi tiếp. Hãy kiểm tra report và chính sách chặn build.

**“Tạo được JAR là đóng gói thành công hoàn toàn.”** Chưa đủ. Một JAR có thể thiếu class, resource, manifest hoặc dependency. Kiểm tra cấu trúc và chạy smoke test tương ứng với loại artifact.

**“Lỗi ở task `<fail>` nghĩa là do task `fail` gây ra.”** Task này có thể chỉ chuyển một kết quả trước đó thành lỗi build. Cần truy tiếp về command exit, kết quả JUnit hoặc điều kiện thiếu artifact.

**“Cùng xuất hiện lúc kiểm thử thì đều là lỗi logic của ứng dụng.”** Một lỗi kết nối database test, thiếu class của runner hoặc sai cấu hình Java có thể thuộc môi trường test. Chỉ khi có bằng chứng test case chạy và assertion không đạt mới nên kết luận failure của hành vi được kiểm thử.

**“Chỉ cần chạy lại target package là biết gói đã ổn.”** Không nhất thiết. Nếu đầu vào là sản phẩm biên dịch cũ hoặc dependency khác phiên, target package có thể tạo ra gói sai. Hãy kiểm tra nguồn tạo ra các tệp đầu vào.

## 11. Tự luyện tập và củng cố

1. Trong một project dùng `<exec>`, đặt `failonerror="false"` và `resultproperty`, rồi thử lệnh trả mã khác `0`. Bổ sung `<fail>` để build dừng với thông báo có mã thoát.
2. Với dự án có JUnit, tạo một assertion sai và ghi nhận `tests`, `failures`, `errors` trong báo cáo. Sau đó làm thiếu một dependency test để đối chiếu với lỗi không khởi tạo được test.
3. Đóng gói JAR hợp lệ, dùng `jar tf` kiểm tra danh sách class. Tiếp theo sửa `Main-Class` thành tên class sai, thử `java -jar` và giải thích vì sao task `jar` vẫn có thể thành công.
4. Ghi lại cho mỗi tình huống: **giai đoạn phát hiện**, **cơ chế thất bại**, **bằng chứng đầu tiên**, **nguyên nhân gốc** và **thao tác sửa**.

Điểm cần ghi nhớ: trong Apache Ant, **lỗi công cụ con** được nhận diện qua khả năng khởi chạy và trạng thái tiến trình; **lỗi kiểm thử** qua kết quả test và điều kiện thực thi test; còn **lỗi gói phân phối** qua quá trình tạo và chất lượng nội dung của artifact. Khi phân biệt thêm giai đoạn với nguyên nhân, bạn sẽ tránh sửa triệu chứng ở cuối pipeline trong khi lỗi thực bắt đầu ở bước trước.

### Tài liệu tham khảo

- [Apache Ant Manual — Exec task](https://ant.apache.org/manual/Tasks/exec.html)
- [Apache Ant Manual — Java task](https://ant.apache.org/manual/Tasks/java.html)
- [Apache Ant Manual — JUnit task](https://ant.apache.org/manual/Tasks/junit.html)
- [Apache Ant Manual — Jar task](https://ant.apache.org/manual/Tasks/jar.html)
- [Apache Ant Manual — Fail task](https://ant.apache.org/manual/Tasks/fail.html)

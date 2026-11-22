# Tích hợp công cụ phân tích mã qua task ngoài hoặc dòng lệnh

Apache Ant điều phối build bằng project, target và task. Khi dự án cần kiểm tra quy tắc code style, phát hiện lỗi tiềm ẩn hoặc phân tích bytecode, Ant có thể gọi các công cụ chuyên dụng thông qua task ngoài, lệnh dòng lệnh hoặc Ant task do công cụ cung cấp.

Các công cụ thường gặp trong quy trình chất lượng mã gồm:

- **Checkstyle:** kiểm tra quy ước định dạng, cách đặt tên, import và một số quy tắc cấu trúc mã nguồn.
- **PMD:** phân tích source để tìm các mẫu code đáng ngờ, độ phức tạp hoặc cách triển khai có thể cải thiện.
- **SpotBugs:** phân tích bytecode để tìm các mẫu lỗi tiềm ẩn.
- **Các compiler/linter khác:** có thể chạy qua CLI hoặc được tích hợp vào compiler task.

Ant không cần tự hiểu mọi quy tắc phân tích. Nhiệm vụ của Ant là chuẩn bị đầu vào, gọi công cụ đúng cách, thu nhận kết quả, tạo report và quyết định build có tiếp tục hay không. Công cụ phân tích chịu trách nhiệm kiểm tra mã theo bộ quy tắc của nó.

## 1. Vị trí của phân tích mã trong build

Phân tích mã thường được đặt sau khi chuẩn bị source hoặc bytecode và trước khi đóng gói artifact. Tùy công cụ, nó có thể chạy trực tiếp trên source hoặc cần bytecode đã biên dịch.

~~~text
Checkout source
      |
      v
Chuẩn bị dependency và cấu hình
      |
      +--------------------------+
      |                          |
      v                          v
Phân tích source             Biên dịch Java
(Checkstyle, PMD...)              |
      |                          v
      |                    Phân tích bytecode
      |                      (SpotBugs...)
      |                          |
      +------------+-------------+
                   |
                   v
             Tổng hợp kết quả
                   |
          +--------+--------+
          |                 |
       Đạt policy       Vi phạm policy
          |                 |
          v                 v
        Test             Dừng build
          |
          v
       Package
          |
          v
       Release
~~~

Không phải công cụ nào cũng cần chạy sau compile. Checkstyle và nhiều cấu hình PMD có thể phân tích source trực tiếp; SpotBugs cần bytecode và thường chạy sau target compile. Hãy đặt dependency target theo yêu cầu đầu vào thực tế của từng công cụ.

Một build có thể tách các bước thành target:

~~~xml
<target name="checkstyle"/>
<target name="pmd"/>
<target name="compile"/>
<target name="spotbugs" depends="compile"/>
<target name="quality" depends="checkstyle,pmd,spotbugs"/>
<target name="verify" depends="quality,test"/>
~~~

Ví dụ này thể hiện quan hệ tổng quát. Các target phải được định nghĩa đầy đủ và mỗi công cụ cần được cấu hình theo cách tích hợp cụ thể. Nếu công cụ phân tích cần source đã preprocess hoặc generated source, hãy đưa bước chuẩn bị đó vào dependency graph.

## 2. Gọi công cụ ngoài bằng task `<exec>`

Task `<exec>` chạy một executable của hệ điều hành. Đây là cách tổng quát để Ant gọi chương trình phân tích đã được cài đặt hoặc script wrapper của dự án.

Ví dụ gọi một chương trình `code-analyzer`:

~~~xml
<target name="analyze-source">
    <mkdir dir="build/reports"/>
    <exec executable="code-analyzer"
          dir="${basedir}"
          failonerror="true">
        <arg value="--config"/>
        <arg value="config/analysis.yml"/>
        <arg value="--format"/>
        <arg value="xml"/>
        <arg value="--output"/>
        <arg value="build/reports/analysis.xml"/>
        <arg value="src/main/java"/>
    </exec>
</target>
~~~

Các thành phần chính:

- `executable`: tên hoặc đường dẫn chương trình cần chạy.
- `dir`: working directory của tiến trình con. Nếu bỏ qua, tiến trình thường chạy trong thư mục làm việc của Ant.
- `failonerror`: nếu đặt `true`, mã thoát khác 0 làm task thất bại và build có thể dừng.
- `<arg>`: truyền từng đối số riêng cho chương trình.

Nên truyền mỗi đối số bằng một phần tử `<arg value="..."/>` thay vì ghép toàn bộ lệnh thành một chuỗi dài. Cách này tránh lỗi tách khoảng trắng và dấu nháy trong đường dẫn, đặc biệt trên Windows.

Nếu executable không nằm trong `PATH`, hãy dùng property chứa đường dẫn rõ ràng:

~~~xml
<property name="analyzer.executable"
          location="tools/bin/code-analyzer"/>

<target name="analyze-source">
    <exec executable="${analyzer.executable}"
          failonerror="true">
        <arg value="--config"/>
        <arg value="config/analysis.yml"/>
        <arg value="src/main/java"/>
    </exec>
</target>
~~~

Trên Windows, executable có thể là file `.exe` hoặc `.bat`/`.cmd`. Việc gọi script shell có khác biệt theo hệ điều hành và cách Ant khởi chạy tiến trình. Với script cần shell syntax như pipe, redirect hoặc biến shell, nên tạo một script wrapper có tên rõ ràng và gọi wrapper đó theo đúng môi trường thay vì nhồi cú pháp shell vào một đối số `exec`.

### 2.1. Ví dụ gọi Checkstyle qua Java command line

Nếu công cụ được phân phối dưới dạng JAR có entry point dòng lệnh, Ant có thể gọi Java executable và truyền `-jar` cùng các tham số. Ví dụ minh họa với Checkstyle:

~~~xml
<property name="java.exe" location="${java.home}/bin/java"/>
<property name="checkstyle.jar" location="tools/checkstyle-all.jar"/>
<property name="checkstyle.config" location="config/checkstyle.xml"/>
<property name="checkstyle.report" location="build/reports/checkstyle.xml"/>

<target name="checkstyle">
    <mkdir dir="build/reports"/>
    <exec executable="${java.exe}"
          dir="${basedir}"
          failonerror="true">
        <arg value="-jar"/>
        <arg file="${checkstyle.jar}"/>
        <arg value="-c"/>
        <arg file="${checkstyle.config}"/>
        <arg value="-f"/>
        <arg value="xml"/>
        <arg value="-o"/>
        <arg file="${checkstyle.report}"/>
        <arg value="src/main/java"/>
    </exec>
</target>
~~~

Ví dụ giả định JAR được đặt tại `tools/checkstyle-all.jar` và phiên bản Checkstyle được chọn hỗ trợ các tham số CLI tương ứng. Tên artifact phân phối và option có thể khác theo cách đóng gói/phiên bản; hãy dùng đúng JAR và cú pháp của phiên bản dự án đã pin.

Ở đây Ant chỉ gọi tiến trình Java. Checkstyle đọc cấu hình, quét source và ghi report. Nếu Checkstyle trả exit code khác 0 khi có vi phạm theo policy, `failonerror="true"` làm target thất bại. Nếu phiên bản hoặc cấu hình công cụ dùng exit code khác, cần ánh xạ kết quả theo tài liệu của chính công cụ.

### 2.2. Gọi công cụ với các tham số được cấu hình bằng property

Không nên lặp lại literal ở nhiều target. Có thể đưa đường dẫn và tham số dùng chung thành property:

~~~xml
<property name="analysis.src" location="src/main/java"/>
<property name="analysis.config" location="config/analysis.yml"/>
<property name="analysis.report.dir" location="build/reports"/>

<target name="analyze-source">
    <mkdir dir="${analysis.report.dir}"/>
    <exec executable="code-analyzer" failonerror="true">
        <arg value="--config"/>
        <arg file="${analysis.config}"/>
        <arg value="--output"/>
        <arg file="${analysis.report.dir}/analysis.xml"/>
        <arg file="${analysis.src}"/>
    </exec>
</target>
~~~

`location` giúp Ant biểu diễn property dưới dạng đường dẫn được phân giải. Các tham số vẫn được truyền riêng để chương trình nhận đúng từng đối số.

## 3. Gọi Java tool bằng task `<java>`

Nếu công cụ cung cấp một lớp Java có phương thức `main`, có thể dùng task `<java>` thay vì gọi `java` qua `<exec>`. Task này hiểu classpath và có thể gọi một class hoặc JAR Java.

Ví dụ dùng một lớp CLI:

~~~xml
<path id="analyzer.classpath">
    <pathelement location="tools/code-analyzer.jar"/>
    <fileset dir="tools/lib">
        <include name="*.jar"/>
    </fileset>
</path>

<target name="analyze-source">
    <mkdir dir="build/reports"/>
    <java classname="com.example.analysis.Main"
          fork="true"
          failonerror="true">
        <classpath refid="analyzer.classpath"/>
        <arg value="--config"/>
        <arg value="config/analysis.yml"/>
        <arg value="--output"/>
        <arg value="build/reports/analysis.xml"/>
        <arg value="src/main/java"/>
    </java>
</target>
~~~

`classname` là tên lớp chứa `main`; `classpath` cung cấp JAR cần thiết; `fork="true"` chạy công cụ trong JVM riêng; `failonerror="true"` khiến lỗi của tiến trình Java làm task thất bại.

Dùng fork hữu ích khi tool cần JDK riêng, JVM option riêng hoặc thư viện có thể xung đột với classpath của Ant. Nếu `fork="false"`, lớp chạy trong JVM Ant và dùng classloader của Ant; điều này có thể gây xung đột phiên bản thư viện hoặc giới hạn khả năng tách cấu hình JVM.

Không phải công cụ nào cũng cung cấp Java main class công khai. Nếu công cụ chỉ có executable native hoặc script CLI, dùng `<exec>` phù hợp hơn.

## 4. Tích hợp Ant task do công cụ cung cấp

Một số công cụ phân tích cung cấp Ant task riêng. Khi đó, task được đăng ký bằng `<taskdef>` hoặc antlib, sau đó gọi trực tiếp như task Ant bình thường.

Mô hình tổng quát:

~~~xml
<path id="analysis.task.classpath">
    <pathelement location="tools/analysis-ant-task.jar"/>
    <fileset dir="tools/analysis-lib">
        <include name="*.jar"/>
    </fileset>
</path>

<taskdef name="codecheck"
         classname="com.example.analysis.ant.CodeCheckTask"
         classpathref="analysis.task.classpath"/>

<target name="analyze-source">
    <mkdir dir="build/reports"/>
    <codecheck config="config/analysis.yml"
               source="src/main/java"
               report="build/reports/analysis.xml"
               failOnViolation="true"/>
</target>
~~~

Đây là ví dụ cấu trúc minh họa; `com.example.analysis.ant.CodeCheckTask` và các thuộc tính `config`, `source`, `report`, `failOnViolation` phải được thay bằng tên lớp và thuộc tính thật do thư viện task cung cấp.

Ưu điểm của Ant task chuyên biệt:

- Cấu hình có thể được thể hiện bằng thuộc tính và nested element thay vì chuỗi CLI.
- Task có thể tích hợp trực tiếp với Path, FileSet, Property và log của Ant.
- Có thể trả lỗi hoặc tạo property theo cách phù hợp với build.
- Dễ chia sẻ cấu hình qua target và reference.

Đổi lại, dự án phải quản lý JAR task và các thư viện phụ thuộc của nó, bảo đảm task tương thích với phiên bản Ant/JDK, đồng thời theo dõi thay đổi API của task qua các lần nâng cấp.

Không phải mọi công cụ đều còn duy trì Ant task chính thức. Trước khi dùng, cần kiểm tra tài liệu của phiên bản đang chọn. Nếu task cũ không tương thích với JDK/Ant hiện tại, gọi CLI có thể là cách tích hợp đơn giản và ít phụ thuộc hơn.

## 5. Xử lý exit code và quyết định build có thất bại hay không

Một công cụ phân tích thường trả exit code để báo kết quả. Quy ước phổ biến là `0` nghĩa là chạy thành công và mã khác `0` nghĩa là có lỗi hoặc vi phạm, nhưng ý nghĩa chính xác tùy công cụ và cấu hình.

Cách đơn giản nhất là để Ant dừng khi chương trình trả mã khác 0:

~~~xml
<exec executable="code-analyzer" failonerror="true">
    <arg value="src/main/java"/>
</exec>
~~~

Nếu muốn lưu exit code rồi xử lý ở bước sau, có thể dùng `resultproperty`:

~~~xml
<target name="analyze-source">
    <exec executable="code-analyzer"
          failonerror="false"
          resultproperty="analysis.exit">
        <arg value="src/main/java"/>
    </exec>

    <condition property="analysis.ok">
        <equals arg1="${analysis.exit}" arg2="0"/>
    </condition>

    <fail unless="analysis.ok"
          message="Code analysis failed with exit code ${analysis.exit}"/>
</target>
~~~

Trong ví dụ, `failonerror="false"` cho phép task trả về để build file kiểm tra `analysis.exit`. Nếu exit code bằng 0, condition đặt property `analysis.ok`; nếu không, `<fail>` làm target thất bại.

Cần phân biệt lỗi không khởi chạy được executable với lỗi do chính công cụ trả về. `failonerror` điều khiển việc xử lý exit code khác 0; `failifexecutionfails` điều khiển lỗi khi Ant không thể tạo tiến trình. Trong pipeline chất lượng mã, thông thường nên giữ `failifexecutionfails="true"` để không âm thầm bỏ qua việc công cụ chưa chạy.

Nếu công cụ trả exit code 0 ngay cả khi có violation nhưng chỉ ghi kết quả vào report, `failonerror` không thể tự biết report có lỗi. Khi đó cần dùng option fail-on-violation của công cụ, task chuyên biệt, hoặc bước đọc report để chuyển số violation vượt ngưỡng thành lỗi build.

## 6. Thu thập log và report

Một quy trình phân tích hữu ích cần giữ lại report để lập trình viên xem vị trí và loại vi phạm. Có thể để công cụ tự ghi report qua tham số `--output`, hoặc chuyển stdout/stderr của tiến trình vào file.

Ví dụ dùng output và error file của task `<exec>`:

~~~xml
<target name="analyze-source">
    <mkdir dir="build/reports"/>
    <mkdir dir="build/logs"/>
    <exec executable="code-analyzer"
          failonerror="true"
          output="build/logs/analyzer-out.log"
          error="build/logs/analyzer-error.log">
        <arg value="--format"/>
        <arg value="xml"/>
        <arg value="--output"/>
        <arg value="build/reports/analyzer.xml"/>
        <arg value="src/main/java"/>
    </exec>
</target>
~~~

Ở ví dụ này, công cụ tự tạo XML report; Ant lưu stdout và stderr riêng. Tùy phiên bản Ant và cách cấu hình redirector, có thể chọn append/overwrite hoặc xử lý output khác. Hãy kiểm tra report được tạo ở đúng vị trí và không bị ghi đè ngoài ý muốn.

Một số nguyên tắc:

- Tạo thư mục report trước khi gọi tool.
- Dùng định dạng máy đọc được như XML, JSON hoặc SARIF nếu CI cần tổng hợp kết quả.
- Lưu report như build artifact khi pipeline thất bại để vẫn có dữ liệu điều tra.
- Tách report của từng tool để dễ xác định nguồn cảnh báo.
- Đặt tên report theo module hoặc build variant nếu phân tích nhiều phần của dự án.
- Không chỉ dựa vào console output nếu cần truy vấn lịch sử vi phạm.

## 7. Tạo quality gate từ kết quả phân tích

Chạy công cụ và tạo report chưa đủ để tạo quality gate. Dự án cần quy định vi phạm nào làm build thất bại.

Một số chính sách phổ biến:

- Dừng build khi có bất kỳ lỗi phân tích nào.
- Dừng khi số lỗi mức blocker/critical lớn hơn 0.
- Cho phép warning nhưng không cho phép error.
- Không để số vi phạm mới tăng so với baseline hiện tại.
- Chỉ áp dụng quy tắc nghiêm ngặt cho phần source mới hoặc phần code được thay đổi.

Nếu công cụ hỗ trợ exit code theo violation, hãy cấu hình trực tiếp theo tài liệu của nó. Nếu tool chỉ sinh report, có thể thêm bước kiểm tra report bằng script hoặc task riêng. Không nên dùng grep chuỗi console output làm parser lâu dài vì định dạng thông báo có thể thay đổi theo phiên bản và locale.

Có thể chia target để chạy từng công cụ và có một target tổng hợp:

~~~xml
<target name="checkstyle">
    <!-- Run Checkstyle and create its report. -->
</target>

<target name="pmd">
    <!-- Run PMD and create its report. -->
</target>

<target name="static-analysis" depends="checkstyle,pmd"/>

<target name="verify" depends="static-analysis,test"/>
~~~

Nếu một target phân tích thất bại với lỗi làm build dừng, target tổng hợp không thể được xem là đạt. Nếu muốn chạy hết mọi công cụ để thu thập tất cả report trước khi thất bại, hãy cấu hình từng bước để lưu kết quả, rồi có một target cuối đánh giá tổng hợp và gọi `<fail>` khi policy không đạt.

## 8. Phân biệt lỗi thực thi công cụ với vi phạm chất lượng

Có hai nhóm failure khác nhau:

| Loại lỗi | Ví dụ | Cách xử lý |
|---|---|---|
| Không chạy được tool | Không tìm thấy executable/JAR, thiếu JDK, sai quyền, sai classpath | Dừng build và sửa môi trường/cấu hình |
| Tool chạy nhưng mã nguồn vi phạm | Sai naming rule, lỗi static analysis, bug pattern | Đọc report, sửa source hoặc điều chỉnh policy có kiểm soát |
| Tool chạy nhưng không tạo report | Sai đường dẫn, quyền ghi, cấu hình output | Kiểm tra tham số và thư mục đích |
| Tool chạy, trả exit code 0 nhưng report có violation | Tool không dùng violation làm exit status | Đọc report hoặc bật chế độ fail-on-violation |
| Tool không phân tích đúng tập source | Sai include/exclude hoặc working directory | Kiểm tra đầu vào được truyền cho tool |

Không nên chuyển mọi lỗi thực thi thành warning rồi tiếp tục build. Nếu tool không khởi động, nhóm không có kết quả phân tích và quality gate chưa được thực hiện. Hãy giữ riêng trạng thái “không phân tích được” và “đã phân tích, có vi phạm”.

## 9. Quản lý phiên bản công cụ và môi trường chạy

Công cụ phân tích cũng là dependency của build. Nếu máy local dùng Checkstyle phiên bản mới còn CI dùng phiên bản cũ, cùng source có thể tạo report khác nhau hoặc một số option không được hỗ trợ.

Nên quản lý rõ:

- Phiên bản công cụ và checksum của JAR/executable.
- Phiên bản JDK dùng chạy công cụ.
- Phiên bản cấu hình ruleset.
- Đường dẫn source và generated source được phân tích.
- Phiên bản Ant và task adapter nếu dùng Ant task chuyên biệt.
- Tham số CLI, encoding và thư mục làm việc.

Nếu công cụ là Java application, có thể chạy qua JDK đã chọn:

~~~xml
<property name="analysis.java" location="${java.home}/bin/java"/>
~~~

Tuy nhiên, `java.home` ở đây là runtime của JVM đang chạy Ant. Nếu tool yêu cầu JDK khác, hãy khai báo executable riêng thay vì giả định Ant runtime luôn phù hợp.

Tránh tải phiên bản mới nhất của tool trong mỗi lần build. Hãy pin version để build hôm nay và build sau vài tháng dùng cùng bộ quy tắc và cùng engine, trừ khi nhóm chủ động nâng cấp.

## 10. Tích hợp trong CI/CD

Trong CI, Ant thường được gọi sau checkout và chuẩn bị JDK/dependency. Pipeline có thể chạy:

~~~bash
ant clean
ant static-analysis
ant test
ant package
~~~

Hoặc gom các bước thành một target `verify`:

~~~bash
ant clean verify
~~~

CI chịu trách nhiệm:

- Cài đặt hoặc cung cấp đúng phiên bản công cụ phân tích.
- Cung cấp credential nếu công cụ cần truy cập dịch vụ bên ngoài.
- Lưu report và log dưới dạng artifact của pipeline.
- Đánh dấu job thất bại nếu quality gate không đạt.
- Hiển thị report trong giao diện CI nếu có hỗ trợ định dạng tương ứng.
- Giữ lịch sử kết quả để theo dõi xu hướng chất lượng.

Ant chịu trách nhiệm gọi target và chuyển trạng thái task. Công cụ phân tích chịu trách nhiệm phát hiện vấn đề. CI thu thập và hiển thị kết quả. Phân chia rõ các trách nhiệm giúp nhóm xác định lỗi nằm ở build script, tool, source hay agent CI.

## 11. Tổ chức build file cho nhiều công cụ

Khi tích hợp nhiều công cụ, có thể gom property và path dùng chung ở cấp project, nhưng nên giữ target riêng theo từng công cụ:

~~~xml
<property name="source.dir" location="src/main/java"/>
<property name="report.dir" location="build/reports"/>
<property name="tools.dir" location="tools"/>

<target name="prepare-analysis">
    <mkdir dir="${report.dir}"/>
</target>

<target name="checkstyle" depends="prepare-analysis">
    <!-- Invoke Checkstyle CLI or its Ant task. -->
</target>

<target name="pmd" depends="prepare-analysis">
    <!-- Invoke PMD CLI or its Ant task. -->
</target>

<target name="spotbugs" depends="compile,prepare-analysis">
    <!-- Analyze compiled classes. -->
</target>

<target name="static-analysis" depends="checkstyle,pmd,spotbugs"/>

<target name="verify" depends="static-analysis,test"/>
~~~

Cấu trúc này giúp gọi riêng `ant checkstyle` khi phát triển, hoặc gọi `ant verify` trong CI. Nếu SpotBugs cần compile output, dependency `compile` được khai báo rõ; các công cụ source analysis không nhất thiết phải chờ compile.

Không nên đặt mọi lệnh vào một target lớn khó đọc. Khi mỗi công cụ có target riêng, có thể cấu hình report, version, exit code và quality gate phù hợp với đặc điểm của nó.

## 12. Những lỗi thường gặp khi tích hợp công cụ phân tích

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `Execute failed: ...` hoặc không tìm thấy executable | Tool chưa cài, sai `PATH` hoặc sai đường dẫn | Dùng property chỉ rõ executable và kiểm tra trên CI agent |
| `Could not find or load main class` | Classpath tool thiếu JAR hoặc sai classname | Kiểm tra tool distribution và classpath |
| Tool chạy local nhưng không chạy CI | Khác JDK, quyền, working directory hoặc biến môi trường | In môi trường, pin tool và cấu hình executable rõ ràng |
| Đường dẫn có khoảng trắng bị tách sai | Ghép nhiều tham số thành một chuỗi command | Dùng từng nested `<arg>` riêng |
| Build xanh dù report có lỗi | Tool trả exit code 0 hoặc Ant không kiểm tra report | Cấu hình fail-on-violation hoặc thêm bước đánh giá report |
| Build dừng nhưng không có report | Tool thất bại trước khi ghi report hoặc output path sai | Kiểm tra log, quyền ghi và tham số output |
| Phân tích thiếu file | Pattern/working directory sai | Kiểm tra danh sách source được chọn |
| SpotBugs không có dữ liệu phân tích | Chưa compile hoặc sai thư mục class | Nối target phân tích với target compile và kiểm tra output |
| Cảnh báo khác nhau giữa máy | Tool version/ruleset/JDK khác nhau | Pin phiên bản tool và lưu cấu hình trong repository |
| Tool Ant task báo lỗi class loading | Thiếu task JAR hoặc dependency xung đột với Ant | Kiểm tra `taskdef`, classpath và tương thích phiên bản |

Khi debug, bật log chi tiết của Ant và chạy riêng target công cụ. Kiểm tra command, working directory, exit code, stdout/stderr và report path. Đừng vội tắt `failonerror` để làm build xanh nếu chưa hiểu lý do tool trả mã lỗi.

## 13. Quy trình triển khai thực tế

Khi thêm một công cụ phân tích vào dự án Ant, có thể thực hiện theo trình tự:

1. Chọn công cụ và xác định nó phân tích source hay bytecode.
2. Pin phiên bản tool, JDK cần chạy và cấu hình ruleset.
3. Quyết định gọi bằng `<exec>`, `<java fork="true">` hay Ant task chính thức.
4. Tạo property cho executable/JAR, config, source và report directory.
5. Tạo target riêng, truyền tham số thành các `<arg>` rõ ràng.
6. Xác định exit code nào thể hiện lỗi thực thi và exit code nào thể hiện violation.
7. Bảo đảm report được tạo và giữ lại khi CI thất bại.
8. Thêm target vào quality/verify theo dependency graph.
9. Chạy local và CI để xác nhận cùng tool version, source set và policy.
10. Ghi lại cách chạy target riêng để lập trình viên có thể dùng trong quá trình phát triển.

Với dự án đã có nhiều cảnh báo, có thể bắt đầu bằng việc tạo baseline và ngăn số vi phạm mới tăng. Sau đó nhóm xử lý dần các cảnh báo cũ rồi mới chuyển sang chính sách nghiêm ngặt hơn. Baseline phải được quản lý rõ ràng để không trở thành cách che giấu lỗi mới.

## Kết luận

Ant tích hợp công cụ phân tích mã bằng cách điều phối tiến trình và nhận kết quả. `<exec>` phù hợp với executable hoặc CLI; `<java fork="true">` phù hợp với công cụ Java có main class cần JVM riêng; `<taskdef>` dùng khi thư viện cung cấp Ant task chuyên biệt. Một tích hợp đáng tin cậy cần pin phiên bản tool, truyền tham số rõ ràng, giữ report, phân biệt lỗi chạy tool với vi phạm code và ánh xạ exit code thành quality gate. Đặt các target phân tích vào luồng `verify` trước package/release để CI có thể dừng phát hành khi chất lượng mã không đạt chính sách của dự án.
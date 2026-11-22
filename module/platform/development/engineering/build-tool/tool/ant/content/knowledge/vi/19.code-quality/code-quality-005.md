# Đặt ngưỡng chất lượng và truyền lỗi kiểm tra về kết quả build

## 1. Quality gate trong quy trình Ant

Một build không chỉ cần biên dịch thành công. Trước khi đóng gói hoặc phát hành, dự án còn có thể cần kiểm tra quy tắc định dạng, lỗi tiềm ẩn, kết quả kiểm thử, độ bao phủ mã và các tiêu chí kỹ thuật khác.

**Quality gate** là một điều kiện có thể đo lường để quyết định build được tiếp tục hay phải thất bại. Ví dụ:

- Không cho phép lỗi Checkstyle.
- Tất cả unit test phải thành công.
- Độ bao phủ dòng lệnh phải đạt tối thiểu 80%.
- Không cho phép lỗi phân tích tĩnh có mức nghiêm trọng cao.
- Công cụ kiểm tra dependency phải xác nhận không có thư viện thuộc danh sách cấm.

Ant điều phối các bước này bằng target và dependency giữa target. Các công cụ chuyên dụng thực hiện việc phân tích, còn Ant chịu trách nhiệm nhận kết quả, quyết định có tiếp tục hay không và trả mã thoát phù hợp cho terminal hoặc CI.

Luồng thường gặp:

```text
compile
   |
   v
test -----------+
   |            |
   v            v
static analysis |
   |            |
   v            |
coverage check  |
   |            |
   +------v-----+
          |
          v
       verify
          |
          v
       package
          |
          v
       release
```

Một quality gate cần trả lời rõ ba câu hỏi:

1. **Đo điều gì?** Ví dụ số lỗi, mức độ nghiêm trọng hoặc tỷ lệ coverage.
2. **Ngưỡng đạt là bao nhiêu?** Ví dụ không có lỗi mức Error hoặc line coverage tối thiểu 80%.
3. **Khi không đạt thì làm gì?** Ghi báo cáo, đánh dấu property thất bại, dừng target hoặc trả mã thoát khác 0.

Nếu chỉ tạo báo cáo mà không có bước biến kết quả thành lỗi build, CI có thể vẫn báo thành công dù chất lượng không đạt yêu cầu.

## 2. Chọn ngưỡng chất lượng có thể đo lường

Không phải mọi cảnh báo đều cần làm build thất bại. Trước khi cấu hình, hãy phân loại tiêu chí theo mức ảnh hưởng.

| Nhóm kiểm tra | Ví dụ tiêu chí | Hành vi thường dùng |
|---|---|---|
| Định dạng và quy ước | Không có vi phạm quy tắc bắt buộc | Có thể chặn build |
| Phân tích tĩnh | Không có lỗi nghiêm trọng hoặc lỗi mới | Chặn theo severity hoặc baseline |
| Unit test | Không có test failure hoặc error | Chặn build |
| Coverage | Line coverage tối thiểu 80%, branch coverage tối thiểu 70% | Chặn nếu thấp hơn ngưỡng |
| Dependency | Không có dependency bị cấm hoặc lỗ hổng vượt ngưỡng | Chặn theo chính sách dự án |
| Cảnh báo thông tin | Nợ kỹ thuật đã biết, cảnh báo không chặn phát hành | Ghi báo cáo, theo dõi riêng |

Ngưỡng phải phù hợp với mục đích của dự án. Một thư viện dùng trong hệ thống quan trọng có thể yêu cầu coverage cao và kiểm tra nghiêm ngặt. Một dự án đang tiếp nhận code cũ có thể bắt đầu bằng việc chặn lỗi mới hoặc lỗi mức cao, sau đó tăng ngưỡng theo từng đợt.

Một số nguyên tắc hữu ích:

- Định nghĩa rõ severity nào là lỗi chặn build và severity nào chỉ là cảnh báo.
- Dùng ngưỡng số hoặc tỷ lệ cụ thể, tránh tiêu chí mơ hồ như “coverage phải tốt”.
- Không hạ ngưỡng chỉ để làm cho build hiện tại xanh mà không có lý do được ghi nhận.
- Khi nâng ngưỡng, bảo đảm báo cáo và dữ liệu đầu vào đủ ổn định để nhóm có thể giải thích thay đổi.
- Với dự án cũ có nhiều vi phạm, cân nhắc baseline để chặn vi phạm mới hoặc vi phạm nghiêm trọng trước khi yêu cầu sửa toàn bộ lịch sử.

## 3. Tách bước kiểm tra, báo cáo và quyết định thất bại

Một target chất lượng thường gồm ba phần:

1. Chạy công cụ kiểm tra.
2. Ghi báo cáo để có thể điều tra.
3. Chuyển kết quả không đạt thành lỗi Ant.

Ví dụ tổng quát:

```xml
<target name="quality-check">
    <mkdir dir="build/reports"/>

    <!-- Chạy công cụ kiểm tra tại đây và ghi báo cáo -->

    <fail if="quality.failed"
          message="Quality gate failed. See build/reports for details."/>
</target>
```

Task `fail` làm target thất bại khi điều kiện `if` đúng. Khi Ant gặp lỗi build, tiến trình Ant kết thúc với mã thoát khác 0. CI có thể dựa vào mã thoát này để đánh dấu job thất bại.

Property `quality.failed` phải được đặt bởi bước kiểm tra khi phát hiện vi phạm. Nếu công cụ chỉ ghi cảnh báo ra console mà không cung cấp exit code, property hoặc báo cáo có cấu trúc, Ant không thể tự suy ra quality gate đã thất bại.

Nên dùng báo cáo dạng XML, JSON hoặc định dạng máy đọc được khi cần xử lý tự động. Không nên phân tích văn bản log dành cho con người bằng cách tìm một chuỗi thông báo có thể thay đổi giữa các phiên bản.

## 4. Chặn build bằng Checkstyle

Checkstyle kiểm tra mã Java theo bộ quy tắc được khai báo trong file cấu hình. Các quy tắc có thể quy định cách đặt tên, import, độ dài dòng, cấu trúc mã, Javadoc và nhiều chuẩn khác.

Một bộ quy tắc nằm trong `config/checkstyle.xml`. Ví dụ một phần cấu hình có thể đặt mức severity cho các vi phạm:

```xml
<module name="Checker">
    <property name="severity" value="error"/>

    <module name="TreeWalker">
        <module name="AvoidInlineConditionals"/>
        <module name="UnusedImports"/>
    </module>
</module>
```

Task Ant của Checkstyle được cung cấp bởi thư viện Checkstyle, vì vậy cần đưa JAR tương ứng vào classpath và đăng ký task bằng `taskdef`. Ví dụ:

```xml
<taskdef name="checkstyle"
         classname="com.puppycrawl.tools.checkstyle.ant.CheckstyleAntTask"
         classpath="lib/checkstyle-all.jar"/>

<target name="checkstyle">
    <mkdir dir="build/reports"/>

    <checkstyle config="config/checkstyle.xml"
                failOnViolation="true">
        <fileset dir="src/main/java">
            <include name="**/*.java"/>
        </fileset>
        <formatter type="xml"
                   toFile="build/reports/checkstyle.xml"/>
    </checkstyle>
</target>
```

Trong ví dụ:

- `config` chỉ định bộ quy tắc.
- `fileset` chọn các file Java cần kiểm tra.
- `formatter` tạo báo cáo XML.
- `failOnViolation="true"` yêu cầu task làm build thất bại khi phát hiện vi phạm.

Với cấu hình này, quality gate có ngưỡng là không chấp nhận vi phạm mà Checkstyle báo về. Muốn chỉ chặn một nhóm lỗi, hãy cấu hình severity, filter hoặc suppression theo chính sách của phiên bản Checkstyle đang dùng. Không nên giả định mọi cảnh báo đều có cùng mức độ ảnh hưởng.

Nếu muốn thu thập báo cáo trước rồi mới quyết định ở một target riêng, có thể cấu hình task không dừng ngay khi có vi phạm và sử dụng cơ chế property/report được phiên bản task hỗ trợ. Hãy kiểm tra tài liệu đúng phiên bản Checkstyle đã cài trước khi dựa vào tên thuộc tính đó. Cách đơn giản nhất để chặn ngay là `failOnViolation="true"`.

## 5. Đặt ngưỡng coverage bằng JaCoCo

Độ bao phủ mã (code coverage) cho biết phần mã được thực thi trong lần chạy kiểm thử. JaCoCo có thể đo nhiều loại counter như instruction, line, branch, method và class.

Ant task `check` của JaCoCo cho phép đặt ngưỡng tối thiểu và làm build thất bại nếu rule không đạt. Ví dụ:

```xml
<project name="sample" xmlns:jacoco="antlib:org.jacoco.ant">
    <taskdef uri="antlib:org.jacoco.ant"
             resource="org/jacoco/ant/antlib.xml"
             classpath="lib/jacocoant.jar"/>

    <target name="coverage-check" depends="coverage-report">
        <jacoco:check>
            <rule element="BUNDLE">
                <limit counter="LINE"
                       value="COVEREDRATIO"
                       minimum="0.80"/>
                <limit counter="BRANCH"
                       value="COVEREDRATIO"
                       minimum="0.70"/>
            </rule>
        </jacoco:check>
    </target>
</project>
```

Ví dụ đặt hai giới hạn:

- Line coverage tối thiểu 0.80, tương đương 80%.
- Branch coverage tối thiểu 0.70, tương đương 70%.

JaCoCo cần dữ liệu execution từ các test đã chạy và phân tích trên đúng class file. Vì vậy, target tạo dữ liệu coverage và target báo cáo phải chạy trước `coverage-check`. Tên `coverage-report` trong ví dụ đại diện cho target dự án đã tạo dữ liệu/report; hãy thay bằng target thực tế của build.

Có thể áp dụng rule ở phạm vi bundle, package, class hoặc source file tùy nhu cầu và khả năng của cấu hình JaCoCo. Hãy chọn phạm vi có ý nghĩa với dự án. Một ngưỡng chung cho toàn bộ bundle có thể che khuất một package quan trọng có coverage thấp.

Coverage cao không đồng nghĩa code không có lỗi. Coverage chỉ cho biết code đã được thực thi; nó không chứng minh assertion kiểm tra đầy đủ kết quả hoặc mọi tình huống biên đã được xử lý.

## 6. Truyền lỗi từ unit test về kết quả Ant

Ant có task `junit` để chạy test JUnit. Có thể dùng `failureproperty` và `errorproperty` để ghi nhận kết quả kiểm thử rồi chủ động làm target thất bại sau khi báo cáo được tạo.

Ví dụ:

```xml
<path id="test.classpath">
    <pathelement location="build/classes"/>
    <pathelement location="build/test-classes"/>
    <pathelement location="lib/junit.jar"/>
</path>

<target name="test">
    <mkdir dir="build/test-results"/>

    <junit fork="true"
           haltonfailure="false"
           haltonerror="false"
           failureproperty="tests.failed"
           errorproperty="tests.error">
        <classpath refid="test.classpath"/>
        <formatter type="plain"/>
        <batchtest todir="build/test-results">
            <fileset dir="build/test-classes">
                <include name="**/*Test.class"/>
            </fileset>
        </batchtest>
    </junit>

    <fail if="tests.failed"
          message="Unit tests failed. See build/test-results."/>

    <fail if="tests.error"
          message="Unit tests had execution errors. See build/test-results."/>
</target>
```

`haltonfailure="false"` và `haltonerror="false"` cho phép task hoàn tất phần thu thập kết quả thay vì dừng ngay ở lỗi đầu tiên. Khi có assertion failure hoặc test error, các property tương ứng được đặt. Hai task `fail` phía sau biến kết quả đó thành lỗi build.

Đường dẫn classpath phải chứa class ứng dụng, class test và thư viện JUnit phù hợp với phiên bản Ant/JUnit đang dùng. Trong dự án thực tế, có thể cần thêm dependency test khác.

Nếu muốn dừng ngay khi test thất bại, có thể dùng các thuộc tính halt của task. Tuy nhiên, nếu cần bảo đảm báo cáo được ghi xong trước khi build dừng, mô hình property kết hợp với `fail` sau task thường dễ điều khiển hơn.

## 7. Nhận exit code từ công cụ bên ngoài

Nhiều công cụ phân tích hoặc kiểm tra được gọi qua executable riêng. Ant task `<exec>` có hai thuộc tính quan trọng:

- `failonerror`: quyết định Ant có lập tức thất bại khi chương trình trả mã khác 0 hay không.
- `resultproperty`: lưu mã thoát của chương trình vào một Ant property.

Có thể để Ant nhận mã thoát trước, sau đó tự quyết định bằng `condition` và `fail`:

```xml
<target name="external-quality-check">
    <exec executable="quality-tool"
          failonerror="false"
          resultproperty="quality.exit">
        <arg value="--config"/>
        <arg value="config/quality.yml"/>
        <arg value="--report"/>
        <arg value="build/reports/quality.json"/>
    </exec>

    <condition property="quality.failed">
        <not>
            <equals arg1="${quality.exit}" arg2="0"/>
        </not>
    </condition>

    <fail if="quality.failed"
          message="External quality tool returned ${quality.exit}."/>
</target>
```

Cách hoạt động:

1. Ant gọi chương trình với các tham số đã khai báo.
2. `resultproperty` lưu mã thoát.
3. `condition` đặt `quality.failed` nếu mã thoát khác 0.
4. `fail` làm target thất bại khi property đó tồn tại.

Nếu công cụ dùng mã thoát khác 0 cho cả lỗi cấu hình, lỗi thực thi và vi phạm quality gate, build sẽ chặn trong mọi trường hợp. Điều này thường phù hợp vì không thể xác nhận chất lượng khi công cụ không chạy thành công. Nếu cần phân biệt vi phạm với lỗi hạ tầng, hãy dùng quy ước exit code và báo cáo mà chính công cụ cung cấp.

`exec` không tự hiểu cú pháp tham số của công cụ. Mỗi `<arg>` là một đối số riêng, giúp tránh lỗi quoting và tách chuỗi lệnh theo shell. Đường dẫn executable cần phù hợp với hệ điều hành hoặc được cấu hình rõ trong môi trường CI.

## 8. Dùng fail để đặt quality gate theo điều kiện

Task `fail` là cách tổng quát để chuyển một điều kiện không đạt thành lỗi build. Có thể dùng trực tiếp:

```xml
<target name="check-required-config">
    <available file="config/release.properties"
               type="file"
               property="release.config.available"/>

    <fail unless="release.config.available"
          message="Missing required release configuration."/>
</target>
```

Trong ví dụ, nếu file cấu hình không tồn tại, property không được đặt và `fail` làm target thất bại.

Có thể kết hợp các condition khác để tạo rule phức tạp hơn. Ví dụ, chỉ cho phép đóng gói nếu phiên bản phát hành đã được truyền và thư mục output đã tồn tại:

```xml
<target name="validate-release-inputs">
    <available file="build"
               type="dir"
               property="build.dir.available"/>

    <fail unless="build.dir.available"
          message="Build output directory is missing."/>

    <fail unless="release.version"
          message="Set release.version before packaging."/>
</target>
```

Ở đây `release.version` phải được cung cấp từ property file, `-Drelease.version=...` hoặc một bước cấu hình trước. `fail` kiểm tra property có tồn tại; nếu cần kiểm tra giá trị không rỗng hoặc định dạng phiên bản, hãy thêm condition hoặc task xác thực phù hợp.

## 9. Gom các kiểm tra vào target verify

Để tránh người dùng vô tình đóng gói mà bỏ qua quality gate, hãy đưa các bước bắt buộc vào một target tổng hợp như `verify`, rồi để target phát hành phụ thuộc vào nó.

Ví dụ cấu trúc:

```xml
<target name="compile">
    <!-- Biên dịch mã nguồn -->
</target>

<target name="test" depends="compile">
    <!-- Chạy unit test và fail khi test không đạt -->
</target>

<target name="checkstyle" depends="compile">
    <!-- Phân tích mã và fail khi có vi phạm bị chặn -->
</target>

<target name="coverage-check" depends="test">
    <!-- Kiểm tra ngưỡng coverage -->
</target>

<target name="verify"
        depends="test,checkstyle,coverage-check">
    <echo message="All verification gates passed."/>
</target>

<target name="package" depends="verify">
    <!-- Tạo JAR hoặc artifact -->
</target>

<target name="release" depends="package">
    <!-- Chuẩn bị artifact phát hành -->
</target>
```

Khi chạy:

```bash
ant verify
```

Ant thực hiện các dependency của `verify`. Nếu một target kiểm tra thất bại, target phụ thuộc phía sau không được thực hiện. Vì `package` phụ thuộc vào `verify`, quy trình đóng gói không thể tiếp tục sau khi quality gate bắt buộc không đạt.

Cần nhớ rằng Ant xử lý target theo đồ thị dependency. Những target độc lập có thể đã chạy trước khi một target khác thất bại, tùy thứ tự và quan hệ dependency. Không nên đặt thao tác phát hành hoặc upload vào target độc lập với quality gate.

## 10. Phân biệt cảnh báo, vi phạm và lỗi thực thi

Một công cụ có thể trả về nhiều loại kết quả:

| Kết quả | Ý nghĩa | Hành vi đề xuất |
|---|---|---|
| Pass | Đạt ngưỡng | Tiếp tục build |
| Warning | Có vấn đề cần xem xét nhưng chưa chặn | Ghi báo cáo |
| Violation | Vi phạm rule chất lượng đã đặt | Chặn nếu thuộc severity được chọn |
| Tool error | Công cụ không thể hoàn thành kiểm tra | Thường chặn build vì chưa xác nhận được chất lượng |
| Configuration error | File rule hoặc tham số công cụ sai | Chặn build và sửa cấu hình |

Đừng đánh đồng “không có violation” với “công cụ chạy thành công”. Nếu công cụ không tìm thấy file cấu hình hoặc không thể đọc source, một báo cáo trống không chứng minh code đạt chuẩn.

Với công cụ có phân biệt exit code cho violation và lỗi thực thi, hãy giữ lại thông tin đó trong báo cáo để người xử lý biết cách khắc phục. Với công cụ chỉ trả mã khác 0 chung, hãy ghi log và lưu báo cáo đầu ra nếu có.

Nếu dự án muốn cho phép warning nhưng chặn error, cấu hình mức severity ngay trong công cụ phân tích. Nếu công cụ hỗ trợ ngưỡng số lượng, hãy dùng tính năng native. Khi không có hỗ trợ native, có thể viết bước chuyển đổi từ báo cáo có cấu trúc sang property và `fail`; tránh parse log tự do.

## 11. Truyền kết quả về CI

CI thường chạy Ant qua lệnh như:

```bash
ant -noinput clean verify
```

Nếu target `verify` hoàn tất, tiến trình Ant trả mã thoát thành công. Nếu task `fail`, Checkstyle, JaCoCo, JUnit hoặc một công cụ con làm build thất bại, Ant kết thúc với mã khác 0.

Pipeline cần cấu hình step build để coi mã thoát khác 0 là thất bại. Ví dụ trong một pipeline YAML tổng quát:

```yaml
steps:
  - name: Verify
    run: ant -noinput clean verify
```

Cú pháp chính xác phụ thuộc hệ thống CI, nhưng nguyên tắc chung là không được nuốt hoặc bỏ qua exit code của Ant. Nếu gọi Ant qua script trung gian, script phải truyền lại mã thoát:

```bash
ant verify
status=$?
exit "$status"
```

Nếu script tiếp tục chạy lệnh khác rồi trả về mã thoát của lệnh cuối, lỗi Ant có thể bị che mất. Hãy lưu mã thoát ngay sau lệnh Ant và trả lại mã đó, hoặc dùng cơ chế fail-fast phù hợp với shell.

Ant có tùy chọn `-keep-going` để tiếp tục các target độc lập sau khi một target thất bại. Dù vậy, kết quả cuối của build vẫn là thất bại nếu có lỗi. Tùy chọn này hữu ích khi muốn thu thập thêm kết quả kiểm tra trong cùng lượt chạy; không dùng nó để cho phép đóng gói hoặc phát hành bỏ qua gate bắt buộc.

## 12. Lỗi thường gặp khi đặt quality gate

### Báo cáo có lỗi nhưng build vẫn xanh

Công cụ có thể chỉ ghi báo cáo mà không trả mã thoát khác 0. Hãy bật chế độ fail-on-violation hoặc đọc kết quả có cấu trúc rồi dùng `fail` để chặn.

### Build thất bại nhưng không có báo cáo

Task có thể dừng ngay khi phát hiện vi phạm trước khi formatter ghi file. Kiểm tra cấu hình task, thứ tự formatter và thư mục báo cáo. Nếu công cụ hỗ trợ chế độ thu thập rồi mới fail, dùng chế độ đó để lưu đủ thông tin.

### Quality gate không chạy trong target phát hành

Target phát hành có thể không phụ thuộc vào `verify`. Hãy đưa quan hệ dependency vào build file và kiểm tra target mặc định cũng như các lệnh CI thực sự gọi.

### Property thất bại luôn tồn tại

Ant property thông thường bất biến trong một lần chạy. Nếu property được đặt từ trước, kết quả lần kiểm tra sau không thể ghi đè. Dùng tên property chuyên biệt, không khai báo mặc định cho property kết quả, và tránh chạy lại cùng target trong một project nếu cần kết quả độc lập.

### Công cụ không chạy nhưng build vẫn tiếp tục

Nếu dùng `<exec failonerror="false">`, hãy luôn kiểm tra `resultproperty` sau đó. Nếu không kiểm tra, lỗi khởi chạy hoặc lỗi thực thi có thể bị bỏ qua.

### Ngưỡng coverage không có dữ liệu

JaCoCo cần execution data và class file phù hợp. Đảm bảo test chạy với agent, dữ liệu được ghi ra và report/check đọc đúng file. Không coi thiếu dữ liệu là coverage bằng 0 hoặc là pass tùy tiện; cấu hình gate nên làm rõ trường hợp này.

### Cảnh báo cũ khiến không thể áp dụng gate mới

Dùng baseline hoặc suppression có lý do và chủ sở hữu. Có thể bắt đầu chặn lỗi nghiêm trọng hoặc vi phạm mới, sau đó tăng yêu cầu theo lộ trình. Không thêm suppression toàn cục khiến rule mới mất tác dụng.

## 13. Nguyên tắc vận hành lâu dài

- Đặt quality gate trong target `verify` và bắt buộc target đóng gói/phát hành phụ thuộc vào nó.
- Chọn ngưỡng định lượng và severity rõ ràng cho từng công cụ.
- Lưu báo cáo ở thư mục ổn định như `build/reports` để CI có thể thu thập artifact.
- Phân biệt violation với lỗi khiến công cụ không thể chạy.
- Dùng `failOnViolation`, threshold native, `resultproperty`, `failureproperty` hoặc `errorproperty` khi công cụ hỗ trợ; dùng `fail` để chuyển trạng thái thành kết quả Ant.
- Không bỏ qua exit code của Ant trong script CI.
- Kiểm tra gate bằng cả trường hợp đạt và không đạt để xác nhận pipeline trả đúng trạng thái.
- Khi thay đổi ngưỡng, ghi nhận lý do và tác động để nhóm hiểu vì sao build bị chặn.
- Giữ log và báo cáo đủ thông tin để sửa lỗi mà không phải chạy lại nhiều lần chỉ để tìm vi phạm.

Một quality gate có ích khi ngưỡng được định nghĩa rõ, công cụ tạo ra kết quả có thể kiểm tra và Ant truyền kết quả đó thành trạng thái build. Dùng target `verify` làm điểm hội tụ giúp mọi quy trình đóng gói và phát hành đi qua cùng một bộ kiểm tra; `fail` cùng các thuộc tính kết quả của task giúp lỗi được truyền tới terminal và CI thay vì chỉ nằm trong báo cáo.


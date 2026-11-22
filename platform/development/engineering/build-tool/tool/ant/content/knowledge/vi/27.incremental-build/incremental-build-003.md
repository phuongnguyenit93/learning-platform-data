# Bỏ qua công việc khi đầu ra còn hợp lệ bằng uptodate và điều kiện

## 1. Build tăng dần và kiểm tra tính hợp lệ của đầu ra

Một build có thể tạo ra nhiều đầu ra từ cùng một nhóm đầu vào: biên dịch mã nguồn, sinh tài liệu, chuyển đổi XML, tạo resource hoặc đóng gói dữ liệu. Nếu đầu vào không thay đổi, chạy lại toàn bộ công việc có thể tốn thời gian mà không tạo ra kết quả mới.

**Build tăng dần (incremental build)** chỉ thực hiện lại những công việc có đầu vào thay đổi hoặc đầu ra không còn hợp lệ. Apache Ant hỗ trợ cách làm này bằng task `uptodate`, các task có cơ chế kiểm tra riêng như `javac`, và hệ thống điều kiện để chọn target cần chạy.

Task `uptodate` so sánh thời gian sửa đổi của file nguồn với file đích. Nếu file đích mới hơn tất cả nguồn được kiểm tra, Ant đặt một property. Target phía sau có thể dùng `if` hoặc `unless` để bỏ qua công việc tương ứng.

Luồng cơ bản:

```text
Nguồn và cấu hình
       |
       v
Kiểm tra uptodate
       |
       +---- Đầu ra còn mới ----> Bỏ qua bước tạo
       |
       +---- Đầu ra cũ/thiếu ---> Chạy bước tạo
                                      |
                                      v
                                Cập nhật đầu ra
```

Cần phân biệt ba việc:

- `uptodate` **đánh giá** đầu ra có còn mới theo quy tắc so sánh hay không.
- `condition` **kết hợp** một hoặc nhiều điều kiện thành property.
- `if` và `unless` trên target **quyết định** target có được thực thi hay bị bỏ qua.

`uptodate` không tự chạy hoặc bỏ qua một task tạo file. Nó chỉ cung cấp thông tin để build file quyết định nhánh thực thi.

## 2. Kiểm tra một cặp file bằng task uptodate

Với một file nguồn và một file đích, dùng `srcfile` và `targetfile`:

```xml
<uptodate property="report.current"
          srcfile="src/report.xml"
          targetfile="build/report.html"/>
```

Nếu `build/report.html` mới hơn `src/report.xml`, Ant đặt property `report.current`. Nếu file đích chưa tồn tại hoặc nguồn mới hơn, property không được đặt.

Có thể dùng kết quả để chạy target có điều kiện:

```xml
<target name="check-report">
    <uptodate property="report.current"
              srcfile="src/report.xml"
              targetfile="build/report.html"/>
</target>

<target name="generate-report"
        depends="check-report"
        unless="report.current">
    <mkdir dir="build"/>
    <!-- Chạy công cụ sinh report tại đây -->
    <xslt in="src/report.xml"
          out="build/report.html"
          style="config/report.xsl"/>
</target>

<target name="report" depends="generate-report"/>
```

Khi gọi target `report`:

1. Ant chạy `check-report`.
2. Nếu đầu ra mới hơn nguồn, property `report.current` được đặt.
3. Target `generate-report` bị bỏ qua vì có `unless="report.current"`.
4. Nếu đầu ra cũ hoặc chưa tồn tại, property không được đặt và target tạo lại báo cáo.

`depends` rất quan trọng: target kiểm tra phải chạy trước target sử dụng property. Nếu không có dependency hoặc một thứ tự thực thi tương đương, target sinh báo cáo có thể được đánh giá trước khi kết quả kiểm tra được tạo.

## 3. Kiểm tra nhiều file nguồn cho một đầu ra

Một đầu ra thường phụ thuộc nhiều hơn một file. Ví dụ báo cáo HTML phụ thuộc XML dữ liệu và XSLT stylesheet. Nếu chỉ so sánh XML, thay đổi stylesheet có thể không kích hoạt việc sinh lại báo cáo.

Task `uptodate` hỗ trợ phần tử lồng nhau `srcfiles` để kiểm tra nhiều file nguồn với một file đích:

```xml
<uptodate property="report.current"
          targetfile="build/report.html">
    <srcfiles dir="${basedir}">
        <include name="src/report.xml"/>
        <include name="config/report.xsl"/>
    </srcfiles>
</uptodate>
```

Property chỉ được đặt khi file đích mới hơn tất cả file nguồn được chọn. Nếu một nguồn mới hơn đầu ra, báo cáo cần được tạo lại.

Có thể mở rộng tập nguồn bằng pattern:

```xml
<uptodate property="docs.current"
          targetfile="build/docs/index.html">
    <srcfiles dir="docs-src">
        <include name="**/*.xml"/>
        <include name="**/*.xsl"/>
        <include name="**/*.properties"/>
    </srcfiles>
</uptodate>
```

Khi dùng `srcfiles`, hãy bảo đảm FileSet thực sự chọn tất cả đầu vào có ảnh hưởng đến đầu ra. Nếu bỏ sót template, file cấu hình hoặc resource phụ thuộc, Ant có thể kết luận đầu ra còn mới dù kết quả đã không còn phản ánh đầy đủ nguồn hiện tại.

Nếu task tạo nhiều đầu ra độc lập từ nhiều nguồn, hãy cân nhắc mapper để ánh xạ từng nguồn sang file đích tương ứng thay vì so sánh toàn bộ nguồn với một đầu ra chung.

## 4. Ánh xạ nhiều nguồn sang nhiều đầu ra bằng mapper

Trong một số quy trình, mỗi file nguồn tạo ra một file đích có tên tương ứng. Ví dụ, mỗi file XML trong `src/data` tạo một file HTML trong `build/data`.

Có thể dùng `srcfiles` cùng `mapper`:

```xml
<uptodate property="data.outputs.current">
    <srcfiles dir="src/data">
        <include name="**/*.xml"/>
    </srcfiles>
    <mapper type="glob"
            from="*.xml"
            to="${basedir}/build/data/*.html"/>
</uptodate>
```

Mapper mô tả cách chuyển tên file nguồn thành tên file đích. Ant kiểm tra các cặp tương ứng; property chỉ được đặt khi các đầu ra được ánh xạ đều tồn tại và mới hơn nguồn tương ứng.

Ví dụ với nguồn `customers.xml`, mapper trên tạo đường dẫn đích `build/data/customers.html`. Với nguồn trong thư mục con, phần đường dẫn tương đối được giữ theo quy tắc của mapper.

Khi chọn mapper:

- Dùng `glob` khi phép biến đổi tên file có quy luật đơn giản.
- Dùng mapper phù hợp khác nếu cần thay đổi phần mở rộng, tiền tố hoặc cấu trúc đường dẫn phức tạp hơn.
- Bảo đảm đích ánh xạ trùng với đường dẫn mà task tạo file thực sự sử dụng.
- Kiểm tra trường hợp một nguồn không có đầu ra tương ứng hoặc một đầu ra có nhiều nguồn cùng tác động.

Không phải mọi phép biến đổi đều có thể biểu diễn chính xác bằng mapper. Nếu một task tạo một archive tổng hợp từ nhiều file, hãy so sánh toàn bộ tập nguồn với archive đó thay vì giả lập ánh xạ một-một.

## 5. Dùng condition để kết hợp uptodate với điều kiện khác

Task `condition` cho phép đặt property khi một biểu thức logic đúng. Các điều kiện lồng nhau phổ biến gồm:

- `and`: tất cả điều kiện con phải đúng.
- `or`: ít nhất một điều kiện con đúng.
- `not`: đảo kết quả của điều kiện con.
- `isset`: kiểm tra một property đã tồn tại.
- `available`: kiểm tra file, directory, class hoặc resource có sẵn.
- `equals`: so sánh hai giá trị.
- `uptodate`: kiểm tra quan hệ thời gian giữa file nguồn và file đích.

Ví dụ chỉ bỏ qua việc tạo báo cáo khi nguồn đã có, đầu ra còn mới và người dùng không yêu cầu tạo lại:

```xml
<target name="check-report">
    <condition property="report.skip">
        <and>
            <available file="src/report.xml" type="file"/>
            <uptodate srcfile="src/report.xml"
                      targetfile="build/report.html"/>
            <not>
                <isset property="force.report"/>
            </not>
        </and>
    </condition>
</target>

<target name="generate-report"
        depends="check-report"
        unless="report.skip">
    <mkdir dir="build"/>
    <xslt in="src/report.xml"
          out="build/report.html"
          style="config/report.xsl"/>
</target>
```

Khi người dùng gọi:

```bash
ant report
```

target kiểm tra sẽ đánh giá ba điều kiện. Nếu cả ba đúng, `report.skip` được đặt và bước sinh báo cáo bị bỏ qua.

Để ép chạy lại:

```bash
ant -Dforce.report=true report
```

Property `force.report` tồn tại nên điều kiện `not/isset` sai; `report.skip` không được đặt và target sinh báo cáo được thực thi.

Ở ví dụ trên, nếu stylesheet `config/report.xsl` cũng ảnh hưởng đến đầu ra, cần đưa stylesheet vào phép kiểm tra freshness. Có thể dùng task `uptodate` với `srcfiles` ở target kiểm tra riêng, hoặc dùng một điều kiện phù hợp với toàn bộ tập đầu vào. Không chỉ kiểm tra file XML rồi giả định mọi dependency khác đều không đổi.

## 6. Kết hợp điều kiện với property và target if/unless

Các thuộc tính `if` và `unless` của target kiểm tra **property có tồn tại hay không**:

- `if="name"`: target chạy khi property `name` đã được đặt.
- `unless="name"`: target chạy khi property `name` chưa được đặt.

Chúng không đánh giá giá trị chuỗi của property như một biểu thức boolean. Nếu property có giá trị `false`, nó vẫn tồn tại và `if="name"` vẫn cho phép target chạy.

Ví dụ:

```xml
<condition property="skip.tests">
    <and>
        <isset property="tests.completed"/>
        <equals arg1="${tests.completed}" arg2="true"/>
    </and>
</condition>

<target name="run-tests" unless="skip.tests">
    <!-- Chạy bộ unit test -->
</target>
```

Trong ví dụ này, condition chỉ đặt `skip.tests` khi cả property `tests.completed` tồn tại và có giá trị `true`. Target `run-tests` bị bỏ qua khi property `skip.tests` đã được đặt.

Nếu muốn kiểm tra một property có giá trị cụ thể, dùng `equals`. Nếu chỉ muốn kiểm tra property đã được khai báo hay chưa, dùng `isset`. Không dùng `if` hoặc `unless` như phép so sánh chuỗi.

## 7. Ví dụ hoàn chỉnh cho bước sinh tài liệu tăng dần

Giả sử dự án sinh một trang HTML tổng hợp từ nhiều file XML và stylesheet. Target `check-docs` xác định tài liệu đã mới hay chưa; target `generate-docs` chỉ chạy khi cần.

```xml
<project name="incremental-docs" default="docs" basedir=".">
    <property name="docs.src" value="docs-src"/>
    <property name="docs.output" value="build/docs/index.html"/>
    <property name="docs.stylesheet" value="config/docs.xsl"/>

    <target name="check-docs">
        <uptodate property="docs.current"
                  targetfile="${docs.output}">
            <srcfiles dir="${basedir}">
                <include name="${docs.src}/**/*.xml"/>
                <include name="${docs.stylesheet}"/>
            </srcfiles>
        </uptodate>
    </target>

    <target name="generate-docs"
            depends="check-docs"
            unless="docs.current">
        <mkdir dir="build/docs"/>
        <xslt in="docs-src/index.xml"
              out="${docs.output}"
              style="${docs.stylesheet}"/>
        <echo message="Documentation regenerated."/>
    </target>

    <target name="docs" depends="generate-docs">
        <echo message="Documentation is ready: ${docs.output}"/>
    </target>
</project>
```

Lần chạy đầu tiên, `build/docs/index.html` chưa tồn tại nên Ant tạo tài liệu. Ở lần chạy tiếp theo, nếu đầu ra mới hơn tất cả file XML và stylesheet được chọn, target sinh tài liệu bị bỏ qua.

Khi sửa một file XML hoặc stylesheet, phép so sánh không còn đạt và tài liệu được tạo lại. Những file khác không thay đổi không làm target phải chạy thêm một lần riêng; cả tập nguồn được đánh giá trước khi quyết định.

Trong ví dụ, `xslt` nhận `index.xml` làm input chính. Nếu các XML khác cũng được stylesheet hoặc bước sinh tài liệu đọc, chúng vẫn cần nằm trong tập nguồn freshness. Tập nguồn của `uptodate` phải phản ánh đúng dependency thực tế của tác vụ tạo đầu ra.

## 8. Để task tự xử lý incremental khi có hỗ trợ

Không phải lúc nào cũng cần bọc một task bằng `uptodate`. Một số task Ant đã có cơ chế incremental riêng.

Ví dụ:

- `javac` chỉ biên dịch những source file cần thiết dựa trên class output và trạng thái source.
- `copy` có thể dùng `overwrite`, `preservelastmodified` và các bộ chọn để kiểm soát việc copy.
- `sync` chỉ đồng bộ nội dung cần thiết giữa nguồn và đích theo chính sách của task.
- Một số task tạo archive hoặc resource có thể có tùy chọn cập nhật hoặc chỉ xử lý file thay đổi.

Với `javac`, nên để task compiler quản lý quan hệ source/class thay vì chỉ dùng một property `uptodate` duy nhất cho toàn bộ thư mục. Một mapper một-một từ `.java` sang `.class` không thể mô tả đầy đủ trường hợp một source tạo nhiều class, inner class, generated source hoặc dependency giữa các class.

Hãy dùng `uptodate` khi có đầu ra rõ ràng và quan hệ phụ thuộc có thể biểu diễn đáng tin cậy. Khi task đã có incremental logic phù hợp, ưu tiên dùng cơ chế native của task để tránh tạo thêm một lớp kiểm tra có thể bỏ sót dependency.

## 9. Timestamp, dependency và giới hạn của uptodate

`uptodate` chủ yếu so sánh thời gian sửa đổi của file. Nó không đọc nội dung để xác minh hai file giống nhau hoặc đầu ra có đúng logic.

Điều này dẫn đến một số giới hạn:

- Nếu nội dung nguồn thay đổi nhưng timestamp được giữ nguyên hoặc bị đặt lùi, phép so sánh có thể không phát hiện thay đổi.
- Nếu file đích bị cập nhật timestamp nhưng nội dung sai hoặc tạo dở dang, Ant vẫn có thể coi nó mới hơn nguồn.
- Nếu một dependency không nằm trong tập nguồn, thay đổi dependency đó không kích hoạt tạo lại.
- Nếu đồng hồ giữa các máy hoặc filesystem có độ phân giải timestamp khác nhau, kết quả có thể khó dự đoán ở ranh giới thời gian.
- Nếu tác vụ phụ thuộc biến môi trường, tham số build, phiên bản công cụ hoặc dữ liệu bên ngoài, chỉ so sánh file nguồn có thể chưa đủ.

Với build cần độ tin cậy cao, hãy cân nhắc thêm các dependency phi-file vào cơ chế quyết định. Có thể tạo một file stamp hoặc metadata chứa phiên bản tool, tham số quan trọng và fingerprint cấu hình; khi những giá trị đó thay đổi, bước tạo đầu ra phải chạy lại.

Nếu cần xác định đầu vào thay đổi theo nội dung thay vì timestamp, dùng checksum hoặc một cơ chế fingerprint phù hợp. Task `uptodate` không phải công cụ xác minh tính toàn vẹn nội dung.

## 10. Quản lý property và ép chạy lại

Ant property thông thường là bất biến trong một lần chạy project: sau khi một property được đặt, task khác không thể ghi đè giá trị của nó.

Vì vậy:

- Không khai báo trước property kết quả `uptodate` với giá trị mặc định.
- Dùng tên property riêng cho từng phép kiểm tra.
- Đặt bước kiểm tra trong dependency chạy trước target sử dụng kết quả.
- Không kỳ vọng chạy lại cùng target trong một lần Ant invocation sẽ xóa hoặc tính lại property cũ.
- Dùng một property điều khiển riêng như `force.report` để ép chạy lại.

Ví dụ lệnh:

```bash
ant -Dforce.report=true report
```

Nếu cần chế độ force áp dụng cho nhiều bước, có thể dùng một property chung `force` và kết hợp `not/isset` trong các condition. Hãy thống nhất tên property giữa build file, script và CI.

Đừng đặt `force=false` rồi nghĩ rằng `isset` sẽ trả về false. Property vẫn tồn tại. Nếu cần kiểm tra giá trị, dùng `equals` hoặc condition phù hợp với kiểu dữ liệu.

## 11. Xử lý nhiều target phụ thuộc cùng một kết quả

Khi nhiều target cùng cần một file được sinh tăng dần, hãy tập trung phép kiểm tra vào một target chung:

```xml
<target name="check-schema">
    <uptodate property="schema.current"
              srcfile="schema/model.xml"
              targetfile="build/schema.json"/>
</target>

<target name="generate-schema"
        depends="check-schema"
        unless="schema.current">
    <!-- Sinh schema.json -->
</target>

<target name="validate-data" depends="generate-schema">
    <!-- Dùng build/schema.json -->
</target>

<target name="package" depends="generate-schema">
    <!-- Đóng gói cùng schema.json -->
</target>

<target name="verify" depends="validate-data,package"/>
```

Ant chỉ thực hiện một target một lần trong một lần gọi build, kể cả khi nhiều target cùng phụ thuộc vào nó. Vì vậy, `generate-schema` là điểm dùng chung bảo đảm schema được tạo trước khi các bước cần nó chạy.

Hãy mô tả dependency theo quan hệ thực tế. Nếu `package` cần file được tạo bởi `generate-schema`, nó nên phụ thuộc trực tiếp hoặc gián tiếp vào target tạo file. Không chỉ dựa vào thứ tự viết các target trong build file.

## 12. Lỗi thường gặp

### Đầu ra cũ nhưng target vẫn bị bỏ qua

Kiểm tra tập nguồn có bao gồm tất cả file ảnh hưởng đến đầu ra hay chưa, mapper có ánh xạ đúng tên và đường dẫn hay không, và property có bị đặt từ trước hay không.

### Đầu ra chưa tồn tại nhưng property vẫn được đặt

Xác nhận `targetfile` hoặc đường dẫn do mapper tạo đúng với vị trí mà task sinh file. Kiểm tra có một file khác vô tình được dùng làm target hay không.

### Sửa stylesheet nhưng tài liệu không được tạo lại

Stylesheet chưa được đưa vào `srcfiles`. Thêm tất cả template, cấu hình và dữ liệu phụ thuộc vào phép so sánh freshness.

### Target kiểm tra chạy sau target tạo output

Thêm `depends` để bước kiểm tra chạy trước target có `if` hoặc `unless`. Không dựa vào thứ tự khai báo trong XML.

### Đặt property false nhưng target vẫn chạy sai nhánh

`if` và `unless` kiểm tra property có tồn tại. Dùng `condition` và `equals` khi cần kiểm tra giá trị cụ thể.

### Build trên CI bỏ qua một đầu vào mới

Kiểm tra timestamp được checkout hoặc giải nén giữ như thế nào, độ phân giải filesystem, và các file được sinh bởi bước trước. Khi timestamp không đáng tin cậy, dùng checksum hoặc metadata đầu vào.

### Tự dùng uptodate để thay thế incremental compiler

Compiler có thể quản lý quan hệ phụ thuộc phức tạp hơn một cặp source/class. Để `javac` xử lý incremental compile hoặc dùng công cụ build có dependency tracking đầy đủ.

## 13. Nguyên tắc sử dụng

- Dùng `uptodate` khi có thể xác định rõ file nguồn, file đích và quy tắc freshness.
- Với một nguồn và một đích, dùng `srcfile` và `targetfile`.
- Với nhiều nguồn tạo một đầu ra, dùng `srcfiles` cùng `targetfile`.
- Với nhiều cặp nguồn/đích, dùng `srcfiles` và mapper có ánh xạ chính xác.
- Đặt kết quả kiểm tra vào property riêng rồi dùng `if` hoặc `unless` trên target.
- Kết hợp `uptodate` với `condition`, `and`, `or`, `not`, `available`, `isset` hoặc `equals` khi quyết định cần nhiều tiêu chí.
- Đưa mọi file và tham số có ảnh hưởng đến đầu ra vào mô hình dependency.
- Dùng cơ chế incremental có sẵn của task khi nó mô tả dependency tốt hơn.
- Dùng checksum hoặc fingerprint khi timestamp không đủ tin cậy.
- Cung cấp property force để người dùng và CI có thể yêu cầu tạo lại đầu ra.

`uptodate` giúp Ant nhận biết đầu ra nào còn mới so với đầu vào theo timestamp. `condition` cho phép kết hợp kết quả đó với các điều kiện khác, còn `if` và `unless` chọn target cần chạy. Khi dependency được khai báo đầy đủ, thứ tự target rõ ràng và có cơ chế ép chạy lại, build tăng dần có thể tiết kiệm thời gian mà vẫn giữ đầu ra đồng bộ với nguồn.


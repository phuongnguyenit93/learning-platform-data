# Phân biệt đồ thị target với quyết định task có cần tạo lại đầu ra

Trong Apache Ant, một build có hai câu hỏi độc lập:

1. Công việc nào phải chạy trước công việc nào?
2. Khi công việc đến lượt chạy, đầu ra đã mới chưa hay cần tạo lại?

Ant dùng đồ thị target và thuộc tính `depends` để mô tả thứ tự thực hiện. Việc xác định một tệp có cần được tạo lại hay không thuộc về từng task và các cơ chế kiểm tra đầu vào/đầu ra như timestamp, `uptodate` hoặc `dependset`.

Nếu nhầm lẫn hai lớp này, build có thể có thứ tự đúng nhưng vẫn làm lại công việc không cần thiết. Ngược lại, một output đã lỗi thời có thể bị giữ lại nếu build không mô hình hóa đủ các dependency của nó.

## 1. Hai câu hỏi khác nhau trong một build

Giả sử dự án có ba bước: biên dịch Java, tạo báo cáo từ template và đóng gói JAR. Đồ thị target có thể là:

```text
compile --------+
                +----> package
generate-report-+
```

Đồ thị này cho biết `package` phải chạy sau `compile` và `generate-report`. Nó không cho biết source đã thay đổi chưa, báo cáo có còn mới hay JAR đã tồn tại với nội dung đúng chưa.

| Khía cạnh | Đồ thị target | Kiểm tra trạng thái đầu ra |
|---|---|---|
| Câu hỏi | Target nào chạy trước? | Task có cần làm lại công việc? |
| Cơ chế | `depends` | Timestamp, `uptodate`, `dependset` |
| Phạm vi | Điều phối target | Một task hoặc nhóm file |
| Kết quả | Thứ tự thực hiện | Chạy, bỏ qua hoặc vô hiệu hóa output |

Một target có thể được gọi ở mọi lần build, trong khi task bên trong nó bỏ qua công việc nếu output đã cập nhật. Đây là nền tảng của incremental build trong Ant.

## 2. depends mô tả thứ tự, không phải cache

Ví dụ:

```xml
<target name="compile">
    <javac srcdir="src" destdir="build/classes"/>
</target>

<target name="test" depends="compile">
    <echo message="Run tests"/>
</target>

<target name="package" depends="compile,test">
    <jar destfile="dist/app.jar" basedir="build/classes"/>
</target>
```

Khi chạy `ant package`, Ant thực hiện prerequisite theo đồ thị. Vì `test` cũng phụ thuộc vào `compile`, target `compile` chỉ chạy một lần trong cùng project invocation.

Điều đó không có nghĩa Ant cache target `compile` qua nhiều lần chạy. Mỗi lệnh Ant tạo một project invocation mới; Ant lại duyệt dependency graph và gọi task bên trong target. Task mới quyết định có cần làm việc thật hay không:

- `javac` kiểm tra source và class output để xác định lớp nào cần biên dịch.
- `copy` mặc định có thể bỏ qua tệp đích đã mới hơn hoặc bằng tệp nguồn.
- `uptodate` đặt property nếu output đã cập nhật so với input được khai báo.
- `dependset` có thể xóa một nhóm output khi dependency đã lỗi thời.

Vì vậy, `depends` không phải cơ chế cache và không tự động làm cho build trở thành incremental.

## 3. javac có kiểm tra đầu ra hiện có

Task `javac` kiểm tra source file và class file tương ứng trong thư mục output. Các lớp thường cần biên dịch lại nếu class output chưa tồn tại hoặc source mới hơn class output.

```xml
<property name="src.dir" location="src/main/java"/>
<property name="classes.dir" location="build/classes"/>

<target name="compile">
    <mkdir dir="${classes.dir}"/>
    <javac
        srcdir="${src.dir}"
        destdir="${classes.dir}"
        includeantruntime="false"
        encoding="UTF-8"/>
</target>
```

Mỗi lần chạy `ant compile`, target vẫn được thực thi. Tuy nhiên, nếu class output tồn tại và mới hơn source tương ứng, `javac` có thể bỏ qua việc biên dịch các lớp đó.

Để kiểm tra timestamp có ý nghĩa, hãy dùng một `destdir` ổn định, giữ output tương ứng với đúng source tree và bảo đảm timestamp source phản ánh thay đổi thực tế.

### Giới hạn của incremental compile

Timestamp source/class không đại diện cho mọi yếu tố ảnh hưởng đến bytecode. Ví dụ:

- Một JAR trong classpath được cập nhật nhưng source không đổi.
- Compiler options hoặc JDK thay đổi.
- Annotation processor hoặc công cụ sinh mã thay đổi.
- Một property cấu hình ảnh hưởng đến nội dung được biên dịch.

Trong các trường hợp này, output cũ có thể không còn phù hợp dù source vẫn cũ hơn class file. Hãy chủ động vô hiệu hóa output, dùng thư mục build mới hoặc chạy target `clean` trước khi compile. Không giả định `javac` tự phát hiện mọi thay đổi trong môi trường.

## 4. copy cũng có quy tắc cập nhật riêng

Task `copy` mặc định so sánh timestamp nguồn và đích. Nếu tệp đích đã tồn tại và không cũ hơn nguồn, Ant thường bỏ qua thao tác copy.

```xml
<target name="copy-resources">
    <mkdir dir="build/classes"/>
    <copy todir="build/classes">
        <fileset dir="src/main/resources"/>
    </copy>
</target>
```

Target `copy-resources` vẫn chạy mỗi lần được gọi. Task `copy` tự quyết định tệp nào cần sao chép dựa trên trạng thái nguồn và đích.

Nếu muốn copy bất kể timestamp, dùng `overwrite`:

```xml
<copy
    file="config/default.properties"
    tofile="build/classes/default.properties"
    overwrite="true"/>
```

Khi bật `overwrite="true"`, task copy lại tệp ngay cả khi đích mới hơn. Cách này phù hợp khi chủ đích là luôn thay thế output bằng nội dung nguồn, nhưng sẽ bỏ qua lợi ích của việc không copy khi không cần thiết.

Thuộc tính `preservelastmodified` giữ timestamp gốc của tệp khi copy:

```xml
<copy todir="build/classes" preservelastmodified="true">
    <fileset dir="src/main/resources"/>
</copy>
```

Điều này hữu ích khi timestamp của tệp đích được dùng làm đầu vào cho bước incremental tiếp theo.

## 5. Dùng uptodate để kiểm tra một đầu ra

Task `uptodate` so sánh tài nguyên nguồn với tài nguyên đích và đặt một property nếu output đã cập nhật.

```xml
<target name="check-report">
    <uptodate
        property="report.current"
        srcfile="src/report-template.xml"
        targetfile="build/report.xml"/>
</target>
```

Nếu `build/report.xml` tồn tại và không cũ hơn `src/report-template.xml`, property `report.current` được đặt. Nếu output chưa tồn tại hoặc nguồn mới hơn đích, property không được đặt.

### Kết hợp uptodate với target unless

```xml
<project name="report-build" default="generate-report" basedir=".">

    <target name="check-report">
        <uptodate
            property="report.current"
            srcfile="src/report-template.xml"
            targetfile="build/report.xml"/>
    </target>

    <target
        name="generate-report"
        depends="check-report"
        unless="report.current">

        <mkdir dir="build"/>
        <xslt
            in="src/report-template.xml"
            out="build/report.xml"
            style="src/report.xsl"/>
    </target>

</project>
```

Khi target `generate-report` được yêu cầu:

1. Ant chạy prerequisite `check-report` trước.
2. Task `uptodate` đặt `report.current` nếu output đã mới.
3. Ant kiểm tra điều kiện `unless` của target `generate-report`.
4. Nếu property tồn tại, phần thân target bị bỏ qua; nếu chưa tồn tại, task `xslt` tạo lại báo cáo.

Điều kiện `if` và `unless` trên target kiểm tra **sự tồn tại của property**, không kiểm tra chuỗi giá trị là `true` hay `false`.

Task `uptodate` chỉ biết các nguồn và đích được khai báo. Nếu báo cáo còn phụ thuộc vào stylesheet `src/report.xsl` hoặc file cấu hình khác, bạn cần đưa các đầu vào đó vào phép kiểm tra. Bỏ sót dependency có thể khiến output được xem là mới dù thực tế đã lỗi thời.

## 6. Kiểm tra nhiều nguồn và ánh xạ đầu ra

Một output có thể phụ thuộc vào nhiều tệp nguồn. Task `uptodate` hỗ trợ tập nguồn và mapper để xác định các tên đích tương ứng. Cần chọn dạng khai báo phù hợp với quy tắc tạo output của dự án.

Ví dụ kiểm tra một báo cáo tổng hợp dựa trên nhiều file dữ liệu bằng một output đại diện:

```xml
<target name="check-index">
    <uptodate
        property="index.current"
        targetfile="build/index.html">
        <srcfiles dir="src/pages" includes="**/*.xml"/>
    </uptodate>
</target>
```

Ví dụ này minh họa việc tập nguồn được kiểm tra so với một output đại diện. Khi nhiều nguồn tạo ra nhiều output tương ứng, hãy dùng mapper để mô tả chính xác phép ánh xạ nguồn-đích. Khi nhiều nguồn cùng tạo một file tổng hợp, cần bảo đảm tất cả nguồn tham gia đều được kiểm tra; chỉ kiểm tra một cặp source-target sẽ không đủ.

## 7. Dùng dependset để vô hiệu hóa một nhóm output

Task `dependset` so sánh các tập nguồn và tập đích. Nếu phát hiện dependency không còn hợp lệ, task xóa các target file được khai báo để bước tạo đầu ra phía sau có thể tạo lại chúng.

Ví dụ:

```xml
<target name="invalidate-generated">
    <dependset>
        <srcfileset dir="src/schema">
            <include name="**/*.xsd"/>
        </srcfileset>
        <targetfileset dir="build/generated">
            <include name="**/*.java"/>
        </targetfileset>
    </dependset>
</target>
```

Trong ví dụ, file schema là nguồn và file Java sinh ra là output. Khi dependency bị lỗi thời theo quy tắc của task, các output được chọn sẽ bị xóa. Target sinh mã phía sau có thể kiểm tra output bị thiếu và tạo lại.

```xml
<target name="generate-sources" depends="invalidate-generated">
    <mkdir dir="build/generated"/>
    <!-- Gọi công cụ sinh mã theo cấu hình của dự án -->
</target>
```

Đây là khung điều phối; task sinh mã thực tế có thể là task Ant, script hoặc công cụ riêng. Điểm chính là `dependset` thực hiện việc vô hiệu hóa output trước bước sinh mã.

Khác với `uptodate`, `dependset` không chỉ đặt property để target bỏ qua công việc. Nó có thể xóa nhóm target file khi phát hiện chúng không còn hợp lệ. Hãy đọc tài liệu phiên bản Ant đang dùng để nắm quy tắc so sánh và hành vi khi tập nguồn hoặc tập đích trống; fileset phải bao phủ đầy đủ các đầu vào và đầu ra liên quan.

## 8. Kết hợp đồ thị target với incremental check

Một build có thể dùng cả hai lớp:

```xml
<project name="incremental-demo" default="package" basedir=".">

    <property name="src.dir" location="src/main/java"/>
    <property name="classes.dir" location="build/classes"/>
    <property name="report.file" location="build/report.xml"/>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac
            srcdir="${src.dir}"
            destdir="${classes.dir}"
            includeantruntime="false"
            encoding="UTF-8"/>
    </target>

    <target name="check-report">
        <uptodate
            property="report.current"
            srcfile="src/report-template.xml"
            targetfile="${report.file}"/>
    </target>

    <target name="generate-report"
            depends="check-report"
            unless="report.current">
        <mkdir dir="build"/>
        <xslt
            in="src/report-template.xml"
            out="${report.file}"
            style="src/report.xsl"/>
    </target>

    <target name="package" depends="compile,generate-report">
        <mkdir dir="dist"/>
        <jar destfile="dist/app.jar" basedir="${classes.dir}">
            <fileset dir="build">
                <include name="report.xml"/>
            </fileset>
        </jar>
    </target>

</project>
```

Trong pipeline này:

- Đồ thị target bảo đảm `compile` và `generate-report` hoàn thành trước `package`.
- Task `javac` tự quyết định source nào cần biên dịch lại theo quy tắc incremental của nó.
- Target `generate-report` chạy prerequisite `check-report`; task `uptodate` quyết định có cần thực hiện phần sinh báo cáo hay không.
- Target `package` chạy sau cùng và đóng gói kết quả.

Đồ thị target không bị thay thế bởi incremental check. Ngược lại, incremental check cũng không thay thế quan hệ thứ tự. Hai cơ chế bổ sung cho nhau.

## 9. Khi nào nên dùng clean?

Incremental build giả định output hiện có phản ánh đúng các đầu vào và cấu hình đã được dùng để tạo nó. Khi giả định đó không còn đúng, cần xóa output cũ hoặc dùng thư mục output mới.

```xml
<target name="clean">
    <delete dir="build"/>
    <delete dir="dist"/>
</target>

<target name="rebuild" depends="clean,compile,generate-report,package"/>
```

Chạy `ant rebuild` sẽ xóa output rồi thực hiện lại các bước trong dependency graph.

Clean build hữu ích khi thay JDK, compiler options, dependency/classpath, công cụ sinh mã hoặc khi cần xác minh build có thể tái tạo từ đầu trên CI. Không nên luôn chạy `clean` trước mọi target nếu mục tiêu là incremental build, vì thao tác đó xóa output và khiến mọi task phải làm lại.

## 10. Timestamp không phải lúc nào cũng đủ

Phần lớn cơ chế incremental cơ bản của Ant dựa trên timestamp. Cách này nhanh và đơn giản nhưng có giới hạn:

- Một số công cụ đồng bộ file có thể giữ timestamp cũ dù nội dung đã đổi.
- Đồng hồ giữa các máy lệch nhau có thể làm phép so sánh timestamp sai.
- Output có thể phụ thuộc vào biến môi trường, property, phiên bản JDK, dependency JAR hoặc tham số dòng lệnh.
- Báo cáo có thể phụ thuộc template, stylesheet và cấu hình; chỉ kiểm tra template là chưa đủ.
- Một file tổng hợp có thể phụ thuộc nhiều nguồn; bỏ sót một nguồn khiến output lỗi thời bị giữ lại.

Khi timestamp không đủ, có thể dùng checksum, marker file chứa thông tin cấu hình hoặc quy trình clean/rebuild. Ant có task `checksum` để tính digest file; bạn phải tự thiết kế cách so sánh digest và lưu trạng thái phù hợp.

## 11. Dùng marker file để theo dõi cấu hình build

Giả sử bytecode phụ thuộc vào phiên bản JDK, release level hoặc chế độ compiler. Có thể tạo marker thể hiện cấu hình đã dùng:

```xml
<target name="write-build-config">
    <mkdir dir="build"/>
    <echo file="build/compile-config.txt"
          message="jdk=${java.version};release=${release.version};mode=${compile.mode}"/>
</target>
```

Marker chỉ có ích nếu build so sánh nó với cấu hình mong muốn trước khi compile. Có thể dùng task/script riêng để tạo nội dung tạm và so sánh, hoặc xóa class output khi giá trị cấu hình thay đổi.

Không nên chỉ ghi marker mỗi lần build rồi coi đó là bằng chứng output đã được tạo với cấu hình mới. Marker phải được cập nhật sau khi bước compile thành công; nếu không, một lần compile thất bại có thể để lại marker gây hiểu nhầm cho lần chạy sau.

Một quy trình đơn giản:

1. Tạo chuỗi cấu hình mong muốn.
2. So sánh với marker hiện tại.
3. Nếu khác, xóa class output hoặc chuyển sang thư mục output mới.
4. Biên dịch.
5. Chỉ sau khi compile thành công mới ghi marker tương ứng.

## 12. Quan sát incremental build

Để hiểu task có thực sự làm việc hay không, hãy chạy cùng target nhiều lần và quan sát log:

```bash
ant -verbose compile
ant -verbose compile
```

Ở lần đầu, nếu output chưa tồn tại, compiler sẽ biên dịch các lớp. Ở lần sau, nếu source và class output không thay đổi, `javac` có thể bỏ qua một số hoặc tất cả source.

Để quan sát target condition:

```xml
<target name="check-report">
    <uptodate
        property="report.current"
        srcfile="src/report-template.xml"
        targetfile="build/report.xml"/>
    <echo message="Report current: ${report.current}"/>
</target>
```

Property có thể chưa được thiết lập nếu output không tồn tại hoặc nguồn mới hơn. Khi đó log không hiển thị giá trị property; hãy dùng thông tin đó để xác định vì sao target tạo output sẽ được thực hiện.

Một quy trình thử nghiệm:

1. Xóa output và chạy build lần đầu.
2. Chạy lại mà không sửa source.
3. Sửa một source file rồi chạy lại.
4. Sửa một dependency khác như stylesheet hoặc file cấu hình.
5. Xóa riêng một output rồi chạy lại.
6. Chạy clean build và so sánh kết quả.

Mục tiêu là xác nhận từng loại thay đổi có làm đúng đầu ra được tạo lại hay không.

## 13. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Target chạy mỗi lần dù output không đổi | Nhầm việc target được gọi với việc task phải làm lại | Kiểm tra cơ chế up-to-date của task bên trong target |
| Target không chạy dù output đã lỗi thời | Property kiểm tra được đặt sai hoặc prerequisite kiểm tra không chạy | Kiểm tra `depends`, `uptodate`, `if` và `unless` |
| javac bỏ qua source cần biên dịch lại | Dependency hoặc compiler option thay đổi nhưng không nằm trong timestamp check | Clean output hoặc bổ sung invalidation cho cấu hình |
| Copy không thay tệp đích | Tệp đích có timestamp mới hơn hoặc bằng nguồn | Kiểm tra timestamp; dùng `overwrite` nếu thực sự cần luôn copy |
| Output sinh mã cũ vẫn tồn tại | Chưa có bước invalidation cho dependency đã thay đổi | Dùng `dependset` hoặc kiểm tra up-to-date trước bước sinh mã |
| Báo cáo không được tạo lại khi stylesheet đổi | Chỉ kiểm tra template, bỏ sót stylesheet | Khai báo tất cả input trong quy tắc kiểm tra |
| Build luôn làm lại mọi thứ | Target clean được gọi trước mọi lần build hoặc task luôn overwrite | Tách target incremental và clean/rebuild |
| Output được xem là mới dù nội dung sai | Timestamp không phản ánh thay đổi hoặc dependency bị bỏ sót | Kiểm tra input đầy đủ, cân nhắc checksum hoặc clean build |
| Các lần chạy trên CI có kết quả khác nhau | Workspace/output dùng chung hoặc môi trường khác nhau | Cô lập output, chuẩn hóa JDK và cấu hình build |

## 14. Nguyên tắc thiết kế incremental build

- Dùng `depends` để mô tả thứ tự prerequisite giữa các target.
- Không xem `depends` là cơ chế cache hoặc kiểm tra output.
- Tận dụng quy tắc up-to-date sẵn có của `javac`, `copy` và các task khác.
- Dùng `uptodate` khi cần đặt property để điều kiện hóa một target.
- Dùng `dependset` khi cần vô hiệu hóa một nhóm output có quan hệ với nhiều nguồn.
- Khai báo đủ mọi input ảnh hưởng đến output, kể cả stylesheet, cấu hình và dependency.
- Dùng `clean` hoặc output directory mới khi thay đổi môi trường làm timestamp check không còn đáng tin.
- Giữ target clean riêng để không phá incremental build mặc định.
- Kiểm tra log ở lần build đầu, lần build lặp lại và sau khi thay đổi từng loại input.

## 15. Ghi nhớ

- Đồ thị target trả lời công việc nào chạy trước; kiểm tra up-to-date trả lời task có cần tạo lại output không.
- `depends` sắp xếp prerequisite và không lưu cache qua các lần chạy Ant.
- Target vẫn có thể được gọi trong mỗi build, trong khi task bên trong bỏ qua công việc nếu output đã mới.
- `javac` và `copy` có quy tắc incremental riêng dựa trên trạng thái file.
- `uptodate` đặt property khi target file đã cập nhật so với nguồn được khai báo.
- `if` và `unless` trên target kiểm tra sự tồn tại của property.
- `dependset` có thể xóa nhóm target output khi dependency bị lỗi thời.
- Timestamp chỉ đáng tin khi tất cả đầu vào ảnh hưởng đến kết quả được mô hình hóa đầy đủ.
- Clean build cần thiết khi cấu hình hoặc dependency thay đổi mà incremental check không thể nhận biết.

Một build Ant có thể vừa có dependency graph rõ ràng vừa chỉ tạo lại những đầu ra thực sự cần thiết. Hãy dùng `depends` để điều phối target, tận dụng kiểm tra incremental của task và khai báo đầy đủ quan hệ input/output. Khi hai lớp này được thiết kế riêng và phối hợp đúng, build sẽ dễ theo dõi và tiết kiệm thời gian hơn.

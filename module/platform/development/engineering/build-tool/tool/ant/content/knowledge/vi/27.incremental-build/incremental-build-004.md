# Quản lý nhóm nguồn và đầu ra bằng dependset

Trong một build Ant, một đầu ra đôi khi phụ thuộc vào nhiều tệp đầu vào cùng lúc. Ví dụ, một bộ tài liệu HTML có thể được tạo từ nhiều tệp XML, một stylesheet XSLT chính, các stylesheet được import, DTD hoặc XSD và cả build file. Nếu bất kỳ đầu vào nào thay đổi, toàn bộ nhóm HTML có thể cần được tạo lại.

Task `<dependset>` hỗ trợ loại quan hệ phụ thuộc này. Nó so sánh một nhóm tệp nguồn với một nhóm tệp đích. Nếu phát hiện bất kỳ tệp đích nào cũ hơn bất kỳ nguồn nào, Ant xóa toàn bộ nhóm tệp đích. Sau đó, task tạo đầu ra như `<xslt>`, `<copy>` hoặc một công cụ khác có thể tạo lại các tệp đã bị xóa.

Điểm quan trọng là `dependset` chỉ quản lý tính hợp lệ của nhóm đầu ra bằng cách xóa các tệp cũ. Nó không tự biên dịch, chuyển đổi hoặc tạo lại chúng. Build phải có bước tiếp theo để sinh đầu ra.

## 1. Khi nào cần dependset?

Nhiều task Ant có khả năng tự kiểm tra đầu vào và đầu ra của chúng. Ví dụ, `<javac>` kiểm tra thời gian sửa đổi của mã nguồn và class tương ứng; `<copy>` và `<xslt>` cũng có cơ chế xử lý đầu ra cũ theo cách riêng.

Tuy nhiên, có những quan hệ phụ thuộc mà task tạo đầu ra không biết hoặc không thể tự xác định. Ví dụ:

- Nhiều trang HTML cùng phụ thuộc vào một stylesheet chung.
- Một tài liệu XML phụ thuộc vào DTD hoặc XSD được tham chiếu gián tiếp.
- Một nhóm báo cáo phụ thuộc vào nhiều tệp cấu hình.
- Các tệp sinh ra phụ thuộc vào một script generator hoặc build file.
- Nhiều tệp đầu ra phải được giữ đồng bộ với một tập hợp dữ liệu đầu vào.

Nếu task tạo đầu ra chỉ kiểm tra một phần nguồn, nó có thể không biết một tệp phụ trợ đã thay đổi. `dependset` cho phép khai báo thêm những quan hệ đó ở cấp build.

Ví dụ, task XSLT có thể biết tệp XML và stylesheet được truyền trực tiếp, nhưng không nhất thiết theo dõi đầy đủ DTD hoặc stylesheet được import theo cách dự án cần. Ta có thể khai báo các tệp phụ thuộc đó trong dependset.

## 2. Cách dependset hoạt động

Một dependset có hai nhóm:

- **Source files:** các tệp đầu vào có thể làm cho kết quả trở nên cũ.
- **Target files:** các tệp đầu ra cần bị xóa khi phát hiện không còn hợp lệ theo thời gian sửa đổi.

Task so sánh từng nguồn với các tệp đích. Nếu bất kỳ target nào cũ hơn bất kỳ source nào, toàn bộ target set sẽ bị xóa.

~~~text
Nhóm nguồn
  +-- input-1.xml
  +-- input-2.xml
  +-- main.xsl
  +-- common.xsl
  +-- catalog.dtd
          |
          | so sánh thời gian sửa đổi
          v
Nhóm đầu ra
  +-- input-1.html
  +-- input-2.html
  +-- index.html

Nếu một nguồn mới hơn một target:
  -> xóa toàn bộ nhóm target
  -> task tạo đầu ra chạy lại
~~~

Ví dụ, nếu `common.xsl` thay đổi, mọi trang HTML được khai báo trong targetfileset có thể cần tạo lại. Dependset xóa toàn bộ nhóm HTML để bước XSLT tiếp theo sinh lại chúng.

Đây là cơ chế theo nhóm, không phải cơ chế ghép từng nguồn với một đầu ra tương ứng. Nếu một nguồn thay đổi, tất cả target trong nhóm bị xóa, kể cả những target riêng lẻ có thể không phụ thuộc trực tiếp vào nguồn đó.

## 3. Cú pháp và các phần tử lồng

Task `dependset` nhận các nhóm nguồn và đích thông qua các phần tử lồng:

| Phần tử | Loại dữ liệu | Vai trò |
|---|---|---|
| `srcfileset` | FileSet | Chọn các tệp nguồn theo thư mục và include/exclude |
| `srcfilelist` | FileList | Liệt kê tường minh các tệp nguồn |
| `targetfileset` | FileSet | Chọn các tệp đích sẽ được kiểm tra và có thể bị xóa |
| `targetfilelist` | FileList | Liệt kê tường minh các tệp đích |
| `sources` | Resource collection | Nhóm nguồn tổng hợp, được hỗ trợ từ Ant 1.7 |
| `targets` | Path | Nhóm đường dẫn tệp đích, được hỗ trợ từ Ant 1.7 |

Cần có ít nhất một nhóm nguồn và một nhóm đích. Có thể khai báo nhiều fileset hoặc filelist cho mỗi phía.

Một ví dụ cơ bản:

~~~xml
<dependset>
    <srcfileset dir="src/xml"
                includes="**/*.xml" />
    <srcfileset dir="src/xsl"
                includes="**/*.xsl" />
    <targetfileset dir="build/html"
                   includes="**/*.html" />
</dependset>
~~~

Trong ví dụ:

- Tất cả XML trong `src/xml` là nguồn.
- Tất cả XSL trong `src/xsl` là nguồn.
- Tất cả HTML trong `build/html` là đích.
- Nếu có quan hệ cũ theo thời gian giữa bất kỳ nguồn nào và bất kỳ đích nào, toàn bộ HTML được chọn sẽ bị xóa.

Task không có thuộc tính `srcdir` hoặc `destdir` như một số task xử lý thư mục. Phạm vi nguồn và đích được xác định bằng các phần tử lồng.

## 4. Phân biệt FileSet và FileList

Đây là lựa chọn quan trọng khi xây dựng dependset.

### 4.1. FileSet: chọn các tệp đang tồn tại theo mẫu

FileSet phù hợp khi muốn chọn các tệp khớp mẫu và không coi một tệp không tồn tại là lỗi phụ thuộc. FileSet chỉ đưa các tệp thực tế khớp include/exclude vào tập hợp.

Ví dụ:

~~~xml
<dependset>
    <srcfileset dir="src/schema"
                includes="**/*.xsd" />
    <targetfileset dir="build/generated"
                   includes="**/*.java" />
</dependset>
~~~

Nếu một tệp XSD không tồn tại, nó không được chọn vào source fileset. Vì vậy, việc thiếu tệp không tự động được coi là nguồn mới hơn. Nếu XSD là đầu vào bắt buộc, hãy kiểm tra sự tồn tại riêng bằng `<available>` và `<fail>`.

### 4.2. FileList: liệt kê rõ các tệp bắt buộc

FileList phù hợp khi muốn khai báo chính xác các tệp và coi việc một tệp được liệt kê nhưng không tồn tại là trạng thái cũ.

Ví dụ:

~~~xml
<dependset>
    <srcfilelist dir="config"
                 files="application.properties,logging.properties" />
    <targetfilelist dir="build/generated"
                    files="application-config.xml" />
</dependset>
~~~

Nếu một tệp trong danh sách nguồn hoặc đích không tồn tại, dependset coi nhóm target cần được xóa. Điều này hữu ích khi danh sách tệp là hợp đồng cố định của build và việc thiếu bất kỳ tệp nào cũng có nghĩa đầu ra không còn đáng tin cậy.

### 4.3. So sánh nhanh

| Nhu cầu | Nên dùng |
|---|---|
| Chọn mọi tệp đang tồn tại theo wildcard | FileSet |
| Bỏ qua tệp không tồn tại ngoài dự kiến | FileSet |
| Khai báo một danh sách tệp cố định | FileList |
| Coi tệp được liệt kê nhưng bị thiếu là đầu vào/đầu ra cũ | FileList |
| Lọc theo include/exclude | FileSet |
| Kiểm tra đúng một nhóm file name đã biết | FileList |

Nếu tệp nguồn bắt buộc bị thiếu, dependset có thể xóa target nhưng không tự báo lỗi cấu hình theo cách mà một bước validation riêng thực hiện. Sau đó, generator có thể thất bại vì thiếu nguồn. Nếu muốn thông báo lỗi sớm và rõ ràng, thêm `available` và `fail` trước dependset.

## 5. Ví dụ: tạo lại toàn bộ tài liệu HTML khi nguồn thay đổi

Giả sử dự án tạo HTML từ XML và XSLT:

~~~text
docs/
├── xml/
│   ├── guide.xml
│   └── reference.xml
├── xsl/
│   ├── main.xsl
│   └── common.xsl
└── dtd/
    └── guide.dtd

build/
└── html/
    ├── guide.html
    └── reference.html
~~~

Các trang HTML phụ thuộc vào:

- Mỗi tệp XML tương ứng.
- Stylesheet chính `main.xsl`.
- Stylesheet dùng chung `common.xsl`.
- DTD được dùng trong tài liệu.
- Build file, nếu thay đổi cấu hình xử lý.

Có thể viết:

~~~xml
<property name="docs.xml.dir" location="${basedir}/docs/xml" />
<property name="docs.xsl.dir" location="${basedir}/docs/xsl" />
<property name="docs.dtd.dir" location="${basedir}/docs/dtd" />
<property name="docs.html.dir" location="${basedir}/build/html" />

<target name="generate-docs">
    <mkdir dir="${docs.html.dir}" />

    <dependset verbose="true">
        <srcfileset dir="${docs.xml.dir}"
                    includes="**/*.xml" />
        <srcfileset dir="${docs.xsl.dir}"
                    includes="**/*.xsl" />
        <srcfilelist dir="${docs.dtd.dir}"
                     files="guide.dtd" />
        <srcfilelist dir="${basedir}"
                     files="build.xml" />
        <targetfileset dir="${docs.html.dir}"
                       includes="**/*.html" />
    </dependset>

    <xslt basedir="${docs.xml.dir}"
          destdir="${docs.html.dir}"
          style="${docs.xsl.dir}/main.xsl">
        <include name="**/*.xml" />
    </xslt>
</target>
~~~

Trước khi chạy XSLT, dependset kiểm tra các đầu vào. Nếu có nguồn mới hơn bất kỳ tệp HTML nào, toàn bộ HTML đã chọn bị xóa. Sau đó, task XSLT chạy và tạo lại các trang đầu ra.

Thuộc tính `verbose="true"` yêu cầu Ant ghi thông tin về các target bị xóa và lý do xóa. Thuộc tính này hữu ích khi điều tra vì sao cả nhóm đầu ra được tạo lại. `verbose` được hỗ trợ từ Ant 1.8.0; nếu dự án dùng phiên bản cũ hơn, hãy kiểm tra tương thích hoặc bỏ thuộc tính này.

Ví dụ giả định các nguồn, stylesheet và DTD tồn tại. Nếu DTD bắt buộc nhưng bị thiếu, bước kiểm tra riêng nên báo lỗi trước khi chạy XSLT.

## 6. Ví dụ: một đầu ra phụ thuộc vào nhiều cấu hình

Một tệp cấu hình XML sinh ra có thể phụ thuộc vào nhiều file properties, schema và build script.

~~~xml
<property name="config.src.dir"
          location="${basedir}/config/source" />
<property name="config.schema.dir"
          location="${basedir}/config/schema" />
<property name="generated.dir"
          location="${basedir}/build/generated-config" />

<target name="generate-application-config">
    <mkdir dir="${generated.dir}" />

    <dependset verbose="true">
        <srcfileset dir="${config.src.dir}"
                    includes="**/*.properties" />
        <srcfilelist dir="${config.schema.dir}"
                     files="application-config.xsd" />
        <srcfilelist dir="${basedir}"
                     files="build.xml" />
        <targetfilelist dir="${generated.dir}"
                        files="application-config.xml" />
    </dependset>

    <!-- Gọi generator thực tế để tạo application-config.xml. -->
</target>
~~~

Trong ví dụ, generator được gọi sau dependset. Comment chỉ đánh dấu vị trí cần tích hợp task hoặc chương trình tạo cấu hình của dự án; nó không phải task thực thi.

Nếu một trong các nguồn thay đổi, tệp `application-config.xml` bị xóa. Generator phải tạo lại tệp đó. Nếu generator không được gọi hoặc không tạo được output, build cần thất bại thay vì tiếp tục package một cấu hình thiếu.

## 7. Xử lý nhiều nhóm đầu ra độc lập

Không phải mọi output đều phụ thuộc vào cùng một tập nguồn. Nếu gộp tất cả target vào một dependset, thay đổi nhỏ ở một nhóm nguồn có thể xóa những đầu ra không liên quan.

Ví dụ dự án có tài liệu API và báo cáo vận hành:

~~~xml
<target name="invalidate-api-docs">
    <dependset>
        <srcfileset dir="src/api"
                    includes="**/*.xml" />
        <srcfileset dir="src/api/xsl"
                    includes="**/*.xsl" />
        <targetfileset dir="build/api-docs"
                       includes="**/*.html" />
    </dependset>
</target>

<target name="invalidate-ops-reports">
    <dependset>
        <srcfileset dir="config/reports"
                    includes="**/*.properties" />
        <srcfileset dir="src/report-templates"
                    includes="**/*.xml" />
        <targetfileset dir="build/ops-reports"
                       includes="**/*.pdf" />
    </dependset>
</target>
~~~

Mỗi dependset quản lý một nhóm đầu ra riêng. Nếu cấu hình báo cáo thay đổi, chỉ nhóm PDF bị xóa; tài liệu API không bị ảnh hưởng.

Hãy chia nhóm theo ranh giới phụ thuộc thực tế. Nhóm càng lớn thì càng dễ phải tạo lại nhiều đầu ra; nhóm quá nhỏ lại làm build file dài và khó quản lý. Mục tiêu là để mỗi nhóm target có chung tập nguồn có thể làm nó cũ.

## 8. dependset không ghép từng nguồn với từng đích

Một điểm dễ hiểu nhầm là dependset không tạo quan hệ một-một theo tên file hoặc đường dẫn tương đối.

Giả sử có:

~~~text
sources/
├── a.xml
└── b.xml

targets/
├── a.html
└── b.html
~~~

Khai báo:

~~~xml
<dependset>
    <srcfileset dir="sources" includes="*.xml" />
    <targetfileset dir="targets" includes="*.html" />
</dependset>
~~~

không có nghĩa:

- a.xml chỉ kiểm tra với a.html.
- b.xml chỉ kiểm tra với b.html.

Thay vào đó, mỗi nguồn được so sánh với nhóm target. Nếu bất kỳ target nào cũ hơn bất kỳ nguồn nào, tất cả target trong nhóm bị xóa.

Nếu cần kiểm tra quan hệ một-một hoặc theo mapper, hãy dùng cơ chế phù hợp hơn như `<uptodate>`, mapper hoặc khả năng incremental có sẵn của task tạo đầu ra. Dependset phù hợp khi tất cả target được coi là một nhóm đồng bộ phụ thuộc vào tất cả nguồn.

## 9. Phân biệt dependset với depend và uptodate

Các task này đều liên quan đến dependency hoặc trạng thái cũ, nhưng mục đích khác nhau:

| Task | Phạm vi | Hành động |
|---|---|---|
| `dependset` | Nhóm file nguồn và nhóm file đích bất kỳ | Xóa toàn bộ nhóm target nếu một quan hệ nguồn/đích bị cũ |
| `depend` | Quan hệ phụ thuộc giữa các Java class | Phân tích bytecode và xóa class phụ thuộc vào class đã cũ để buộc biên dịch lại |
| `uptodate` | Kiểm tra một hoặc nhiều nguồn so với đích, thường có mapper | Thiết lập property cho biết đích đã cập nhật hay chưa |
| `javac` | Mã nguồn Java và class output | Tự quyết định source nào cần biên dịch theo cơ chế của task |

Dùng `dependset` khi quan hệ phụ thuộc không thể suy ra trực tiếp từ tên file hoặc nội dung mà task tạo đầu ra biết được. Dùng `depend` khi cần phân tích phụ thuộc giữa Java class. Dùng `uptodate` khi muốn đặt property hoặc điều kiện để quyết định một target có cần chạy hay không.

Ví dụ, không nên thay cơ chế incremental của javac bằng dependset cho toàn bộ thư mục class nếu mục tiêu là chỉ biên dịch lại những lớp thay đổi. Dependset có thể xóa toàn bộ nhóm class target và khiến javac biên dịch lại nhiều hơn cần thiết.

## 10. Thứ tự thực thi: dependset phải chạy trước generator

Dependset chỉ xóa target. Vì vậy, nó phải được thực hiện trước task tạo lại output.

Một target đúng thứ tự:

~~~xml
<target name="prepare-generated-files">
    <dependset>
        <srcfileset dir="src/templates"
                    includes="**/*.xml" />
        <srcfileset dir="src/styles"
                    includes="**/*.xsl" />
        <targetfileset dir="build/generated"
                       includes="**/*.html" />
    </dependset>
</target>

<target name="generate" depends="prepare-generated-files">
    <xslt basedir="src/templates"
          destdir="build/generated"
          style="src/styles/main.xsl">
        <include name="**/*.xml" />
    </xslt>
</target>
~~~

Target `generate` phụ thuộc `prepare-generated-files`, nên dependset chạy trước. Sau khi target fileset bị xóa, XSLT có thể tạo lại các file còn thiếu.

Nếu đặt dependset sau XSLT, build có thể tạo đầu ra rồi lập tức xóa chúng. Nếu không có target tạo lại sau dependset, output sẽ biến mất và các bước package tiếp theo có thể thất bại.

## 11. Xử lý đầu vào hoặc đầu ra bị thiếu

### 11.1. FileList coi tệp bị thiếu là cũ

Khi dùng FileList, một tệp được liệt kê nhưng không tồn tại khiến toàn bộ target set bị xóa. Đây là hành vi hữu ích khi các file đó bắt buộc phải tham gia vào kết quả.

Tuy nhiên, dependset không thay thế validation. Nếu tệp nguồn bắt buộc bị thiếu, generator có thể thất bại sau đó. Để báo lỗi dễ hiểu, thêm kiểm tra:

~~~xml
<target name="validate-schema">
    <available file="config/schema/application-config.xsd"
               type="file"
               property="schema.present" />
    <fail unless="schema.present"
          message="Required schema file is missing" />
</target>
~~~

Sau đó cho target sử dụng dependset phụ thuộc vào validation.

### 11.2. FileSet bỏ qua file không tồn tại

FileSet chỉ chọn những tệp đang tồn tại và khớp mẫu. Nếu một tệp mong đợi bị xóa khỏi source tree, fileset có thể không đưa nó vào nhóm nguồn. Khi sự thiếu vắng đó phải làm đầu ra được tạo lại hoặc phải báo lỗi, dùng FileList cho tệp cố định hoặc thêm bước validation riêng.

### 11.3. Target bị thiếu

Nếu target được liệt kê rõ bằng FileList nhưng không tồn tại, dependset coi nhóm target cần được làm mới. Nếu targetfileset chỉ chọn các file hiện có, các file không tồn tại không nằm trong tập hợp được chọn; task tạo đầu ra tiếp theo vẫn cần có khả năng tạo các file thiếu.

Với output bắt buộc, hãy kiểm tra sau generator bằng `available` và `fail` để chắc chắn file thực sự đã được tạo.

## 12. So sánh thời gian sửa đổi và giới hạn của timestamp

Dependset dựa vào thời gian sửa đổi của tệp, không so sánh nội dung hoặc checksum. Vì vậy:

- Thay đổi nội dung nhưng giữ nguyên timestamp có thể không được phát hiện.
- Sao chép tệp có thể làm timestamp thay đổi tùy cách copy.
- Hệ thống tệp có độ chính xác timestamp khác nhau.
- Đồng hồ giữa các máy hoặc nguồn dữ liệu có thể không đồng bộ.
- Archive được giải nén có thể giữ hoặc đặt lại timestamp tùy công cụ.

Nếu build phụ thuộc vào nội dung chính xác, checksum hoặc hash-based verification có thể cần thiết ở một bước riêng. Dependset phù hợp với build incremental dựa trên timestamp trong môi trường có quy trình cập nhật tệp nhất quán.

Không nên coi dependset là cơ chế phát hiện mọi thay đổi nội dung. Nếu quy trình tạo artifact tải nguồn từ hệ thống khác hoặc đồng bộ giữa máy có clock lệch, hãy cân nhắc bước xác minh bổ sung.

## 13. Dùng verbose để chẩn đoán

Thuộc tính `verbose` giúp xem lý do target bị xóa:

~~~xml
<dependset verbose="true">
    <srcfileset dir="src/xml"
                includes="**/*.xml" />
    <srcfileset dir="src/xsl"
                includes="**/*.xsl" />
    <targetfileset dir="build/html"
                   includes="**/*.html" />
</dependset>
~~~

Ở chế độ verbose, Ant ghi các target bị xóa và thông tin về nguồn/đích khiến nhóm được xem là cũ. Điều này hữu ích khi build bất ngờ tạo lại toàn bộ output.

Nếu build log quá dài, chỉ bật verbose trong lúc điều tra hoặc trong job chẩn đoán. Thuộc tính này không thay đổi quy tắc so sánh, chỉ tăng thông tin log.

## 14. Những trường hợp không nên dùng dependset

Không nên dùng dependset nếu:

- Mỗi nguồn chỉ ảnh hưởng đến một đầu ra riêng và task đã có cơ chế incremental chính xác.
- Cần chỉ xóa những target tương ứng với nguồn đã thay đổi.
- Cần so sánh nội dung thay vì timestamp.
- Đầu ra không thể được tạo lại tự động sau khi bị xóa.
- Nhóm target chứa file người dùng tạo hoặc dữ liệu không thể tái tạo.
- Không có cách xác định rõ thư mục và mẫu target an toàn.

Vì dependset xóa cả nhóm target, hãy chắc chắn tất cả tệp trong nhóm đều là đầu ra do build quản lý và có thể tạo lại. Không đưa tệp nguồn, dữ liệu người dùng hoặc artifact đã phát hành vào targetfileset.

Nếu chỉ cần xóa một nhóm cache được tái tạo dễ dàng, dependset có thể phù hợp. Nếu target là báo cáo đã được người dùng chỉnh sửa thủ công, việc xóa nhóm sẽ gây mất dữ liệu.

## 15. Ví dụ tổng hợp với target verify và generate

Build file sau thể hiện đầy đủ thứ tự kiểm tra nguồn, xóa output cũ, tạo lại tài liệu và xác nhận kết quả:

~~~xml
<project name="documentation-build" default="generate-docs" basedir=".">

    <property name="source.xml.dir"
              location="${basedir}/docs/xml" />
    <property name="source.xsl.dir"
              location="${basedir}/docs/xsl" />
    <property name="source.dtd.dir"
              location="${basedir}/docs/dtd" />
    <property name="output.html.dir"
              location="${basedir}/build/html" />

    <target name="validate-doc-inputs">
        <available file="${source.xsl.dir}/main.xsl"
                   type="file"
                   property="main.stylesheet.present" />
        <available file="${source.dtd.dir}/guide.dtd"
                   type="file"
                   property="guide.dtd.present" />

        <fail unless="main.stylesheet.present"
              message="Missing main XSL stylesheet" />
        <fail unless="guide.dtd.present"
              message="Missing required guide DTD" />
    </target>

    <target name="prepare-doc-output"
            depends="validate-doc-inputs">
        <mkdir dir="${output.html.dir}" />

        <dependset verbose="true">
            <srcfileset dir="${source.xml.dir}"
                        includes="**/*.xml" />
            <srcfileset dir="${source.xsl.dir}"
                        includes="**/*.xsl" />
            <srcfilelist dir="${source.dtd.dir}"
                         files="guide.dtd" />
            <srcfilelist dir="${basedir}"
                         files="build.xml" />
            <targetfileset dir="${output.html.dir}"
                           includes="**/*.html" />
        </dependset>
    </target>

    <target name="generate-docs"
            depends="prepare-doc-output">
        <xslt basedir="${source.xml.dir}"
              destdir="${output.html.dir}"
              style="${source.xsl.dir}/main.xsl">
            <include name="**/*.xml" />
        </xslt>

        <available file="${output.html.dir}/guide.html"
                   type="file"
                   property="guide.html.present" />
        <fail unless="guide.html.present"
              message="Documentation output guide.html was not generated" />
    </target>

</project>
~~~

Đây là ví dụ cấu trúc. Nếu tên HTML được tạo từ tên XML theo một quy tắc khác, hãy điều chỉnh đường dẫn kiểm tra cuối cùng. Nếu có nhiều tài liệu đầu vào, kiểm tra toàn bộ danh sách output bắt buộc thay vì chỉ một file đại diện.

Target `validate-doc-inputs` bảo đảm các nguồn cố định có mặt. Target `prepare-doc-output` chạy dependset trước generator. Target `generate-docs` tạo HTML và xác nhận output quan trọng tồn tại.

## 16. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể xảy ra | Hướng xử lý |
|---|---|---|
| Toàn bộ output bị xóa dù chỉ một nguồn thay đổi | Dependset có tính chất invalidation theo nhóm | Chia thành nhiều nhóm target có nguồn phụ thuộc riêng |
| Nguồn bắt buộc bị thiếu nhưng dependset không phản ứng | Nguồn được chọn bằng FileSet nên file không tồn tại không nằm trong tập hợp | Dùng FileList cho file cố định hoặc thêm available/fail |
| Target không được tạo lại sau khi bị xóa | Dependset chỉ xóa, không sinh output | Đặt generator sau dependset và khai báo thứ tự target |
| Build tạo lại output ở mọi lần chạy | Timestamp nguồn luôn mới hơn target hoặc target không được tạo | Kiểm tra timestamp, đường dẫn và thư mục output |
| Thay đổi nội dung nhưng không làm target bị xóa | Timestamp không đổi hoặc có độ chính xác không đủ | Dùng checksum hoặc cơ chế kiểm tra nội dung riêng |
| Một nhóm output không liên quan cũng bị xóa | Gộp nhiều quan hệ độc lập vào cùng targetfileset | Tách dependset theo nhóm phụ thuộc |
| Không thấy lý do target bị xóa | Chưa bật verbose | Dùng verbose trong lúc điều tra |
| FileList gây invalidation dù file không tồn tại | FileList coi tệp được liệt kê nhưng bị thiếu là out-of-date | Xác nhận file phải tồn tại hoặc chuyển sang FileSet nếu muốn bỏ qua |
| Build không báo thiếu file nguồn rõ ràng | Dependset chỉ invalidates target, không phải bước validation nghiệp vụ | Dùng available và fail trước dependset |
| Targetfileset vô tình chọn cả dữ liệu người dùng | Include quá rộng hoặc trỏ sai thư mục | Giới hạn thư mục output và mẫu file có thể tái tạo |

## 17. Checklist sử dụng dependset

- [ ] Đã xác định rõ nhóm nguồn có thể làm đầu ra cũ.
- [ ] Đã xác định các target đều là output do build quản lý và có thể tạo lại.
- [ ] Đã chọn FileSet hay FileList theo chính sách xử lý file thiếu.
- [ ] Đã khai báo ít nhất một nhóm nguồn và một nhóm đích.
- [ ] Đã hiểu rằng một quan hệ cũ sẽ xóa toàn bộ nhóm target.
- [ ] Đã chia các nhóm target độc lập để tránh invalidation quá rộng.
- [ ] Đã đặt dependset trước task tạo output.
- [ ] Đã có bước generator chạy sau khi target bị xóa.
- [ ] Đã xác thực riêng các nguồn bắt buộc.
- [ ] Đã kiểm tra output sau generator.
- [ ] Đã bật verbose khi cần điều tra việc xóa target.
- [ ] Đã cân nhắc giới hạn của timestamp và nhu cầu checksum.

## 18. Nguyên tắc duy trì

- Dùng dependset cho các quan hệ phụ thuộc theo nhóm mà task tạo đầu ra không tự theo dõi đầy đủ.
- Khai báo nguồn bằng srcfileset hoặc srcfilelist và đích bằng targetfileset hoặc targetfilelist.
- Dùng FileSet để chọn file tồn tại theo mẫu; dùng FileList khi file được liệt kê nhưng bị thiếu phải làm nhóm output cũ.
- Nhớ rằng một target cũ hơn bất kỳ source nào sẽ khiến toàn bộ nhóm target bị xóa.
- Không coi dependset là task tạo output hoặc kiểm tra nội dung.
- Đặt generator sau dependset và bảo đảm generator có thể tạo lại mọi file bị xóa.
- Chia nhóm nguồn/đích theo ranh giới phụ thuộc thực tế.
- Không đưa file người dùng hoặc dữ liệu không thể tái tạo vào target set.
- Dùng verbose để xem lý do invalidation khi cần.
- Bổ sung validation hoặc checksum nếu timestamp không đủ để bảo đảm kết quả.

`dependset` hữu ích khi nhiều đầu ra cần được làm mới cùng nhau vì chúng phụ thuộc vào một nhóm nguồn chung. Khi xác định đúng phạm vi fileset/filelist, hiểu rõ hành vi xóa toàn bộ nhóm và đặt generator đúng sau bước kiểm tra, build Ant có thể quản lý các dependency gián tiếp mà task tạo đầu ra không tự nhận biết.


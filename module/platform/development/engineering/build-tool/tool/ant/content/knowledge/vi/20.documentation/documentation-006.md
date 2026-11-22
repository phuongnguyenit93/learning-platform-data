# Biến đổi báo cáo XML bằng XSLT và quản lý tài nguyên stylesheet

Trong nhiều dự án Java, kết quả kiểm thử, dữ liệu nghiệp vụ hoặc báo cáo build được xuất dưới dạng XML. XML thuận tiện cho việc trao đổi dữ liệu giữa công cụ, nhưng người đọc thường cần một dạng trình bày khác như HTML, văn bản hoặc một cấu trúc XML đã được biến đổi. XSLT (*Extensible Stylesheet Language Transformations*) mô tả quy tắc chuyển đổi một tài liệu XML thành đầu ra mong muốn.

Apache Ant cung cấp task `<xslt>` để chạy một stylesheet trên một tệp XML hoặc trên một nhóm tệp. Task này giúp đưa bước tạo báo cáo vào buildfile: Ant chọn XML nguồn, nạp stylesheet, truyền tham số, gọi bộ xử lý XSLT và ghi kết quả vào thư mục đích.

Để cấu hình ổn định, cần quản lý rõ ba nhóm tài nguyên: XML đầu vào, stylesheet chính cùng các stylesheet được include/import, và các thư viện hoặc tài nguyên mà bộ xử lý XSLT cần để thực thi.

## 1. XSLT và vai trò của stylesheet

XSLT là ngôn ngữ mô tả cách biến đổi một cây XML thành một kết quả khác. Stylesheet XSLT thường là tệp XML có phần tử gốc `xsl:stylesheet` hoặc `xsl:transform`, dùng namespace `http://www.w3.org/1999/XSL/Transform`.

Ví dụ một XML báo cáo đơn giản:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<report>
    <title>Build summary</title>
    <result status="passed">Unit tests</result>
    <result status="failed">Integration tests</result>
</report>
```

Stylesheet có thể biến tài liệu đó thành HTML:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet
    version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

    <xsl:output method="html" encoding="UTF-8" indent="yes" />

    <xsl:template match="/report">
        <html>
            <head>
                <title><xsl:value-of select="title" /></title>
            </head>
            <body>
                <h1><xsl:value-of select="title" /></h1>
                <ul>
                    <xsl:for-each select="result">
                        <li>
                            <strong><xsl:value-of select="@status" /></strong>
                            <xsl:text> - </xsl:text>
                            <xsl:value-of select="." />
                        </li>
                    </xsl:for-each>
                </ul>
            </body>
        </html>
    </xsl:template>

</xsl:stylesheet>
```

Trong stylesheet:

- `xsl:output` mô tả phương thức và encoding của đầu ra.
- `xsl:template match="/report"` chọn phần tử gốc `report` làm ngữ cảnh xử lý.
- `xsl:value-of` lấy giá trị của một nút hoặc biểu thức XPath.
- `xsl:for-each` lặp qua các phần tử `result`.
- Các phần tử HTML được tạo thành kết quả.

Stylesheet là tài nguyên đầu vào của bộ xử lý XSLT, tương tự như XML nguồn. Ant không tự suy ra cách trình bày báo cáo; task `<xslt>` chỉ điều phối việc nạp XML, nạp stylesheet và ghi kết quả.

## 2. Chạy một lần biến đổi bằng xslt

Khi chỉ cần biến đổi một tệp, dùng thuộc tính `in`, `out` và `style`:

```xml
<target name="report-html">
    <mkdir dir="build/reports" />

    <xslt
        in="build/results/report.xml"
        out="build/reports/report.html"
        style="src/xsl/report-to-html.xsl" />
</target>
```

Các thuộc tính có ý nghĩa:

| Thuộc tính | Vai trò |
|---|---|
| `in` | Tệp XML đầu vào cần biến đổi |
| `out` | Đường dẫn tệp kết quả |
| `style` | Stylesheet XSLT dùng để biến đổi |

`style` có thể là đường dẫn tuyệt đối hoặc đường dẫn tương đối theo cách Ant phân giải tài nguyên trong project. Trong buildfile, dùng đường dẫn tương đối từ thư mục dự án thường giúp cấu hình dễ di chuyển giữa máy phát triển và CI.

`in` và `out` phù hợp cho một tài liệu cụ thể. Khi cần xử lý nhiều XML cùng một stylesheet, nên dùng `basedir` và `destdir` để mô tả một tập đầu vào.

## 3. Biến đổi hàng loạt bằng basedir và destdir

Task `<xslt>` có thể quét một thư mục nguồn và tạo một tệp đầu ra cho mỗi XML được chọn:

```xml
<target name="all-reports">
    <xslt
        basedir="build/results"
        destdir="build/html-reports"
        style="src/xsl/report-to-html.xsl"
        includes="**/*.xml"
        excludes="**/raw/**"
        extension=".html" />
</target>
```

Trong ví dụ này:

- `basedir` là gốc chứa các tài liệu XML nguồn.
- `destdir` là gốc chứa các tài liệu đã biến đổi.
- `style` là stylesheet được dùng cho mỗi tài liệu được chọn.
- `includes` giới hạn đầu vào vào các tệp XML ở mọi cấp thư mục.
- `excludes` bỏ qua các tệp trong nhánh `raw`.
- `extension` xác định phần mở rộng của tệp kết quả.

Ant giữ cấu trúc thư mục tương đối từ `basedir` trong `destdir`. Ví dụ:

```text
build/results/
├── summary.xml
└── modules/
    ├── core.xml
    └── web.xml
```

Với phần mở rộng `.html`, kết quả tương ứng:

```text
build/html-reports/
├── summary.html
└── modules/
    ├── core.html
    └── web.html
```

Nhờ đó, các báo cáo từ nhiều module có thể được biến đổi theo cùng một quy tắc mà vẫn giữ được cấu trúc phân cấp.

## 4. Chọn XML đầu vào bằng include và exclude

Khi thư mục nguồn chứa nhiều loại XML, hãy giới hạn chính xác những tài liệu cần biến đổi. Có thể dùng phần tử lồng nhau thay cho thuộc tính danh sách:

```xml
<xslt
    basedir="reports"
    destdir="build/site"
    style="src/xsl/report.xsl"
    extension=".html">

    <include name="**/summary.xml" />
    <include name="**/test-results.xml" />
    <exclude name="**/archive/**" />
</xslt>
```

Mẫu `*` khớp ký tự trong một thành phần đường dẫn; `**` có thể đi qua nhiều cấp thư mục. Các mẫu được đánh giá tương đối với `basedir`.

Không nên quét mọi tệp XML nếu thư mục còn chứa XML cấu hình, metadata hoặc tài liệu không tuân theo schema đầu vào của stylesheet. Một stylesheet có thể giả định các phần tử và thuộc tính nhất định; đưa nhầm loại XML vào có thể tạo kết quả rỗng hoặc gây lỗi XPath.

Nếu danh sách đầu vào được quản lý ở tệp riêng, có thể dùng các cơ chế include/exclude file được hỗ trợ bởi task/MatchingTask trong phiên bản Ant đang sử dụng. Với cấu hình nhỏ, khai báo mẫu ngay trong buildfile thường dễ theo dõi hơn.

## 5. Truyền tham số vào stylesheet

Một stylesheet có thể được dùng cho nhiều môi trường hoặc nhiều loại báo cáo. Thay vì sao chép stylesheet, hãy truyền tham số từ Ant bằng phần tử `<param>`.

Ví dụ stylesheet nhận tham số `reportTitle` và `environment`:

```xml
<xsl:stylesheet
    version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

    <xsl:param name="reportTitle" select="'Build report'" />
    <xsl:param name="environment" select="'local'" />

    <xsl:template match="/report">
        <html>
            <head>
                <title><xsl:value-of select="$reportTitle" /></title>
            </head>
            <body>
                <h1><xsl:value-of select="$reportTitle" /></h1>
                <p>Environment: <xsl:value-of select="$environment" /></p>
                <p>Result: <xsl:value-of select="summary" /></p>
            </body>
        </html>
    </xsl:template>
</xsl:stylesheet>
```

Buildfile truyền giá trị:

```xml
<xslt
    in="build/results/report.xml"
    out="build/reports/report.html"
    style="src/xsl/report.xsl">

    <param name="reportTitle" expression="Nightly build" />
    <param name="environment" expression="staging" />
</xslt>
```

Tên trong `name` phải khớp với tên `xsl:param` trong stylesheet. `expression` là giá trị Ant chuyển cho tham số XSLT; nếu stylesheet cần một biểu thức XPath có kiểu dữ liệu cụ thể, hãy kiểm tra quy tắc chuyển kiểu của XSLT processor đang dùng.

Có thể lấy giá trị từ property của Ant:

```xml
<property name="report.environment" value="development" />

<xslt
    in="build/results/report.xml"
    out="build/reports/report.html"
    style="src/xsl/report.xsl">
    <param name="environment" expression="${report.environment}" />
</xslt>
```

Nhờ property, cùng một target có thể được gọi với giá trị khác nhau qua command line:

```shell
ant -Dreport.environment=production report-html
```

## 6. Tách stylesheet thành nhiều tài nguyên có thể tái sử dụng

Khi báo cáo có nhiều phần trình bày, stylesheet chính có thể trở nên dài và khó bảo trì. XSLT hỗ trợ `xsl:include` và `xsl:import` để chia quy tắc thành nhiều stylesheet.

Ví dụ cấu trúc tài nguyên:

```text
src/xsl/
├── report.xsl
├── common/
│   ├── layout.xsl
│   └── formatters.xsl
└── reports/
    ├── tests.xsl
    └── coverage.xsl
```

Stylesheet chính có thể include các template dùng chung:

```xml
<xsl:stylesheet
    version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

    <xsl:include href="common/layout.xsl" />
    <xsl:include href="common/formatters.xsl" />
    <xsl:include href="reports/tests.xsl" />

    <xsl:template match="/report">
        <html>
            <body>
                <xsl:call-template name="page-header" />
                <xsl:apply-templates select="tests" />
            </body>
        </html>
    </xsl:template>
</xsl:stylesheet>
```

`xsl:include` đưa các khai báo và template từ stylesheet được tham chiếu vào stylesheet chính. `xsl:import` cũng nạp một stylesheet khác nhưng có quy tắc ưu tiên template khác, cho phép stylesheet hiện tại ghi đè một số quy tắc được import. Chọn include khi muốn chia module cùng mức; chọn import khi cần xây dựng stylesheet chuyên biệt dựa trên một stylesheet nền.

Các giá trị `href` tương đối thường được phân giải dựa trên URI của stylesheet chứa khai báo. Vì vậy, nên giữ các stylesheet con trong cấu trúc thư mục ổn định và không di chuyển riêng stylesheet chính mà quên cập nhật các đường dẫn `href`.

## 7. Quản lý đường dẫn và vòng đời stylesheet

Thuộc tính `style` của Ant xác định stylesheet chính. Các stylesheet được `include` hoặc `import` là tài nguyên phụ thuộc của nó. Khi tổ chức thư mục, nên coi cả cây stylesheet là một đơn vị:

```text
src/xsl/
├── report.xsl                 # stylesheet chính
├── common/
│   ├── layout.xsl             # include
│   └── dates.xsl              # include
└── themes/
    ├── light.xsl              # import hoặc include theo thiết kế
    └── dark.xsl
```

Một số nguyên tắc quản lý:

- Giữ stylesheet chính và các file con trong repository cùng dự án.
- Dùng đường dẫn tương đối ổn định trong `href`.
- Đặt tên stylesheet theo trách nhiệm, chẳng hạn layout, formatting, test report hoặc coverage report.
- Không để các file stylesheet được build ghi đè lên thư mục chứa stylesheet nguồn.
- Khi thay đổi một file include/import, cần bảo đảm bước XSLT chạy lại để đầu ra phản ánh thay đổi đó.

Ant có cơ chế kiểm tra thời gian sửa đổi để tránh biến đổi lại mọi tệp nếu đầu ra đã mới hơn đầu vào. Thuộc tính `force="true"` yêu cầu thực hiện lại biến đổi ngay cả khi đầu ra có vẻ đã cập nhật. Điều này hữu ích khi stylesheet hoặc tài nguyên phụ thuộc thay đổi mà timestamp của XML nguồn không thay đổi, hoặc khi muốn tạo lại báo cáo một cách tường minh.

Ví dụ:

```xml
<xslt
    basedir="build/results"
    destdir="build/reports"
    style="src/xsl/report.xsl"
    extension=".html"
    force="true" />
```

Nếu cần biến đổi hàng loạt và stylesheet có thể được sửa trong cùng một lần chạy Ant, thuộc tính `reloadstylesheet` cho phép task nạp lại stylesheet cho mỗi lần biến đổi thay vì tái sử dụng stylesheet đã biên dịch/cached. Đây thường không cần thiết trong build thông thường; chỉ bật khi quy trình thực sự thay đổi stylesheet trong lúc task đang xử lý nhiều tài liệu.

## 8. Phân biệt stylesheet với classpath của XSLT processor

`style` chỉ ra tài liệu XSLT cần áp dụng. `classpath` của task dùng để cung cấp các lớp Java của bộ xử lý XSLT hoặc các thành phần hỗ trợ mà Ant cần nạp. Hai khái niệm này không giống nhau.

Ant sử dụng cơ chế JAXP/TraX để làm việc với XSLT processor. Có thể chọn implementation thông qua cấu hình processor hoặc `TransformerFactory` tùy phiên bản Ant và bộ xử lý được cài đặt.

Ví dụ minh họa khai báo classpath riêng cho processor:

```xml
<path id="xslt.processor.classpath">
    <pathelement location="lib/xslt/processor.jar" />
    <pathelement location="lib/xslt/support.jar" />
</path>

<xslt
    in="build/results/report.xml"
    out="build/reports/report.html"
    style="src/xsl/report.xsl"
    classpathref="xslt.processor.classpath" />
```

Nếu dùng một processor không có sẵn trong runtime Ant, phải cung cấp đúng JAR và các dependency của nó. Một stylesheet XSLT 2.0 hoặc 3.0 cũng cần processor hỗ trợ phiên bản tương ứng; không thể giả định mọi implementation JAXP đều hỗ trợ cùng một tập tính năng.

Khi cần chỉ định lớp `TransformerFactory` cụ thể, kiểm tra thuộc tính `factory` và cơ chế chọn processor trong tài liệu Ant của phiên bản đang dùng. Cấu hình này phụ thuộc vào processor và classloader; nên thử một stylesheet nhỏ trước khi áp dụng vào toàn bộ báo cáo.

## 9. Chọn processor và khả năng tương thích XSLT

XSLT processor thực hiện việc biên dịch stylesheet và biến đổi XML. Khả năng ngôn ngữ phụ thuộc implementation:

| Thành phần | Vai trò |
|---|---|
| JAXP/TraX | API Java để tạo transformer và thực hiện biến đổi |
| TransformerFactory | Nhà máy cung cấp implementation transformer |
| Xalan hoặc implementation tương thích | Có thể xử lý stylesheet theo phạm vi XSLT mà phiên bản hỗ trợ |
| Saxon | Processor phổ biến khi cần các tính năng XSLT mới hơn; phạm vi hỗ trợ phụ thuộc phiên bản/edition |

Ant có thể được cấu hình để dùng processor có sẵn hoặc một processor được thêm qua classpath. Thuộc tính `processor` trong task `<xslt>` và thuộc tính `factory` được dùng theo cơ chế của phiên bản Ant tương ứng; tên processor hợp lệ và cách nạp implementation phải khớp với thư viện thực tế.

Trước khi dùng các tính năng như sequence, function hoặc XPath/XSLT mới, hãy xác định phiên bản XSLT mà stylesheet yêu cầu và phiên bản processor trong môi trường CI. Nếu máy phát triển có Saxon mới nhưng CI chỉ dùng implementation XSLT 1.0 mặc định, cùng stylesheet có thể chạy ở máy này nhưng thất bại ở máy khác.

## 10. Kiểm soát đầu ra bằng xsl:output

Định dạng đầu ra thường được mô tả ngay trong stylesheet bằng `xsl:output`:

```xml
<xsl:output
    method="html"
    encoding="UTF-8"
    indent="yes" />
```

Một số giá trị `method` thường gặp:

| Method | Mục đích |
|---|---|
| `xml` | Tạo tài liệu XML |
| `html` | Tạo đầu ra HTML theo quy tắc serializer |
| `text` | Tạo văn bản thuần, không có cấu trúc markup |

`encoding` xác định encoding đầu ra; `indent` yêu cầu serializer định dạng thụt lề nếu processor hỗ trợ. Với đầu ra XML, có thể khai báo thêm `doctype-public`, `doctype-system` hoặc các thuộc tính output khác theo yêu cầu định dạng.

Nếu task cần ghi một loại đầu ra khác nhau theo từng stylesheet, hãy đặt `xsl:output` phù hợp trong stylesheet tương ứng. Không nên dựa vào phần mở rộng `.html` của tệp đầu ra để quyết định nội dung; extension chỉ là tên tệp, còn phương thức serialize do stylesheet/processor kiểm soát.

## 11. Tổ chức một target tạo báo cáo hoàn chỉnh

Một target báo cáo thường có các bước:

1. Chạy test hoặc tạo XML đầu vào.
2. Tạo thư mục đầu ra.
3. Chọn stylesheet chính.
4. Truyền các tham số cần thiết.
5. Chạy XSLT trên tập XML.
6. Đóng gói hoặc publish các file HTML đã tạo nếu quy trình yêu cầu.

Ví dụ:

```xml
<project name="xml-reporting" default="report">

    <property name="results.dir" value="build/results" />
    <property name="reports.dir" value="build/site/reports" />
    <property name="report.environment" value="local" />

    <target name="prepare-report">
        <mkdir dir="${reports.dir}" />
    </target>

    <target name="report" depends="prepare-report">
        <xslt
            basedir="${results.dir}"
            destdir="${reports.dir}"
            style="src/xsl/report.xsl"
            extension=".html"
            includes="**/*.xml"
            excludes="**/raw/**"
            force="true">

            <param
                name="environment"
                expression="${report.environment}" />
            <param
                name="reportTitle"
                expression="Project build report" />
        </xslt>
    </target>

</project>
```

Có thể chọn môi trường khi gọi Ant:

```shell
ant -Dreport.environment=ci report
```

Target này giả định các XML báo cáo đã tồn tại trong `${results.dir}` và stylesheet cùng các file include/import nằm trong `src/xsl`. Nếu cần chạy test trước, thêm target tạo XML vào `depends` của `report` hoặc tạo target tổng hợp riêng để thể hiện đúng thứ tự.

## 12. Sử dụng catalog cho DTD và entity ngoài

Một tài liệu XML có thể tham chiếu DTD hoặc entity ngoài. Nếu bộ xử lý cần phân giải những tham chiếu đó, Ant hỗ trợ cơ chế XML catalog ở các task có tích hợp XMLCatalog. Catalog ánh xạ public ID hoặc system ID sang tài nguyên đã biết, giúp build không phụ thuộc vào việc tải một địa chỉ từ xa mỗi lần chạy.

Ví dụ cấu hình catalog trong buildfile (tùy task và phiên bản Ant, vị trí khai báo catalog có thể khác):

```xml
<xmlcatalog id="report.catalog">
    <dtd
        publicId="-//EXAMPLE//DTD Report 1.0//EN"
        location="src/dtd/report.dtd" />
</xmlcatalog>
```

Nếu task `<xslt>` trong phiên bản đang dùng hỗ trợ nested `xmlcatalog`, có thể tham chiếu catalog đó trong task. Hãy kiểm tra tài liệu đúng phiên bản Ant và bộ xử lý XML vì việc phân giải DTD/entity phụ thuộc parser được sử dụng.

Catalog phục vụ phân giải DTD/entity của tài liệu XML. Nó không thay thế `xsl:include` hoặc `xsl:import`, vốn là cơ chế XSLT để nạp các stylesheet con.

## 13. Lỗi thường gặp khi biến đổi XSLT

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Ant không tìm thấy stylesheet | Đường dẫn `style` sai hoặc tài nguyên không nằm ở vị trí Ant mong đợi | Kiểm tra đường dẫn từ project base directory và tên file |
| Stylesheet không nạp được file include/import | `href` tương đối sai hoặc stylesheet con không được đóng gói cùng cấu trúc | Giữ cây thư mục stylesheet ổn định và kiểm tra đường dẫn từ stylesheet chứa `href` |
| Không tạo ra báo cáo cho một số XML | Mẫu include/exclude không chọn tệp hoặc thư mục đích chưa đúng | Kiểm tra `basedir`, `destdir` và mẫu đường dẫn tương đối |
| Đầu ra có tên hoặc phần mở rộng không như mong đợi | `extension` hoặc mapper đầu ra không phù hợp | Kiểm tra quy tắc tên đầu ra và phần mở rộng cấu hình |
| Stylesheet không hiểu một hàm hoặc cú pháp XSLT | Processor đang dùng không hỗ trợ phiên bản/tính năng stylesheet | Chọn processor tương thích và khai báo classpath cần thiết |
| Tham số XSLT luôn nhận giá trị mặc định | Tên `<param>` không khớp `xsl:param` hoặc biểu thức được truyền sai | So sánh tên tham số và kiểm tra cách processor diễn giải expression |
| Thay đổi stylesheet nhưng đầu ra không cập nhật | Cơ chế timestamp bỏ qua tệp đích đã mới hơn hoặc stylesheet cache | Dùng `force` khi cần chạy lại; xem xét `reloadstylesheet` cho trường hợp cache |
| HTML có encoding sai | `xsl:output` không khai báo encoding mong muốn | Đặt `encoding="UTF-8"` và bảo đảm đầu vào được đọc đúng encoding |
| Một số XML tạo kết quả rỗng | Cấu trúc XML khác với XPath/template mà stylesheet giả định | Kiểm tra namespace, tên phần tử và XPath trong stylesheet |
| Build không tìm thấy processor tùy chỉnh | Thiếu JAR hoặc dependency trên classpath của Ant/XSLT task | Kiểm tra classpath, TransformerFactory và phiên bản processor |

Khi debug, nên kiểm tra theo thứ tự: XML đầu vào có đúng cấu trúc, Ant có chọn tệp đó, stylesheet chính có nạp được, các include/import có phân giải được, processor có hỗ trợ tính năng cần dùng, và cuối cùng là quy tắc serialize đầu ra.

## 14. Quy trình quản lý tài nguyên stylesheet

Khi đưa XSLT vào dự án Ant, có thể tổ chức theo trình tự sau:

1. Xác định định dạng đầu vào và đầu ra, ví dụ XML báo cáo sang HTML.
2. Tạo stylesheet chính và khai báo `xsl:output` phù hợp với định dạng kết quả.
3. Tách template dùng chung thành stylesheet con bằng `xsl:include` hoặc `xsl:import` khi cần.
4. Giữ đường dẫn `href` tương đối ổn định và quản lý toàn bộ cây stylesheet trong repository.
5. Dùng `in`/`out` cho một tệp; dùng `basedir`/`destdir` và include/exclude cho xử lý hàng loạt.
6. Truyền dữ liệu thay đổi theo môi trường bằng `<param>` thay vì tạo nhiều bản stylesheet gần giống nhau.
7. Chọn XSLT processor có khả năng tương thích với phiên bản stylesheet và cung cấp các JAR cần thiết qua classpath khi dùng implementation ngoài.
8. Xác định khi nào cần `force` hoặc `reloadstylesheet` để kết quả được cập nhật khi tài nguyên XSLT thay đổi.
9. Chạy target trên một XML nhỏ trước, sau đó kiểm tra đầu ra và đưa bước biến đổi vào đồ thị build chính.

Task `<xslt>` kết nối XML nguồn với stylesheet và XSLT processor để tạo báo cáo hoặc tài liệu mới. Khi quản lý stylesheet chính, các file include/import, processor và tham số như những tài nguyên build có cấu trúc rõ ràng, việc biến đổi báo cáo sẽ nhất quán giữa máy phát triển và môi trường CI.

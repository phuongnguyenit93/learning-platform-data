# Biến đổi và xác thực XML bằng xslt, xmlvalidate và XMLCatalog

Apache Ant có thể đưa xử lý XML vào quy trình build thông qua ba thành phần bổ trợ nhau:

- Task `<xmlvalidate>` kiểm tra tài liệu XML có đúng cấu trúc và hợp lệ theo quy tắc được cấu hình hay không.
- Task `<xslt>` áp dụng stylesheet XSLT để biến đổi XML thành HTML, XML khác, văn bản hoặc định dạng đầu ra phù hợp.
- Data type `<xmlcatalog>` cung cấp ánh xạ định danh XML như PUBLIC ID, SYSTEM ID hoặc URI tới tài nguyên cục bộ, giúp parser tìm DTD và entity mà không phải phụ thuộc vào máy chủ bên ngoài.

Một pipeline thường xác thực XML trước, rồi mới biến đổi:

~~~text
XML đầu vào + DTD/XSD + XML Catalog
                |
                v
          xmlvalidate
                |
       Hợp lệ?  |  Không hợp lệ
          |     +------> Dừng build
          v
            xslt
                |
                v
       HTML / XML / output khác
                |
                v
       Đưa vào artifact phát hành
~~~

Tách các bước này thành target riêng giúp build dừng sớm khi XML sai, tái sử dụng catalog và stylesheet, đồng thời làm rõ đầu vào, đầu ra của từng công đoạn.

## 1. Vai trò của từng thành phần

| Thành phần | Chức năng | Khi nào dùng |
|---|---|---|
| `<xmlvalidate>` | Phân tích và kiểm tra XML bằng parser được cấu hình | Kiểm tra XML well-formed, DTD hoặc schema validation trước khi xử lý |
| `<xslt>` | Biến đổi XML theo stylesheet XSLT | Sinh HTML, tài liệu, XML trung gian hoặc nội dung phát hành |
| `<xmlcatalog>` | Ánh xạ PUBLIC/SYSTEM ID hoặc định danh XML sang tài nguyên | Dùng DTD/entity/schema cục bộ và kiểm soát việc phân giải tài nguyên XML |

XML Catalog không tự xác thực tài liệu và cũng không tự biến đổi XML. Nó cung cấp tài nguyên cho parser hoặc task sử dụng. `xmlvalidate` thực hiện validation; `xslt` thực hiện transformation.

## 2. Xác thực XML bằng `<xmlvalidate>`

Một tài liệu XML trước khi được xử lý cần ít nhất phải well-formed: có một root element, thẻ mở/đóng khớp, thuộc tính được đặt trong dấu nháy và các quy tắc cú pháp XML được tuân thủ.

Nếu tài liệu khai báo DTD hoặc được cấu hình với schema, parser có thể kiểm tra thêm tính hợp lệ theo các quy tắc đó. Well-formed và valid là hai khái niệm khác nhau:

- **Well-formed:** tài liệu tuân thủ cú pháp XML.
- **Valid:** tài liệu còn tuân thủ DTD hoặc schema được áp dụng.

Ví dụ XML:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE product SYSTEM "product.dtd">
<product>
    <id>P-100</id>
    <name>Keyboard</name>
    <price currency="USD">49.90</price>
</product>
~~~

Một target kiểm tra file đơn giản:

~~~xml
<target name="validate-product">
    <xmlvalidate file="src/xml/product.xml"
                 failonerror="true"
                 warn="true"/>
</target>
~~~

Các thuộc tính thường dùng:

- `file`: chỉ định một file XML cần kiểm tra.
- `failonerror`: nếu đặt `true`, lỗi validation làm task thất bại và có thể dừng build.
- `warn`: yêu cầu parser/task báo các cảnh báo nếu có.
- `lenient`: điều chỉnh cách task xử lý một số lỗi theo chế độ lenient; không nên bật để che giấu lỗi XML trong pipeline phát hành.
- `classname` và `classpath`/`classpathref`: cho phép chọn parser implementation và cung cấp thư viện parser khi cần.

Khi kiểm tra nhiều file, có thể dùng FileSet để chọn XML đầu vào:

~~~xml
<target name="validate-all-xml">
    <xmlvalidate failonerror="true" warn="true">
        <fileset dir="src/xml">
            <include name="**/*.xml"/>
            <exclude name="**/draft/**"/>
        </fileset>
    </xmlvalidate>
</target>
~~~

Pattern `**/*.xml` chọn file XML ở mọi cấp thư mục bên dưới `src/xml`; thư mục `draft` bị loại. Cần bảo đảm FileSet chỉ chọn những file mà parser có thể xử lý theo cùng một bộ quy tắc. Nếu một số file dùng DTD/schema khác nhau, có thể chia thành nhiều target hoặc nhóm FileSet với cấu hình parser/catalog riêng.

### 2.1. Kiểm tra XML theo DTD

Một tài liệu có thể khai báo DTD bằng SYSTEM ID hoặc PUBLIC ID. Ví dụ:

~~~xml
<?xml version="1.0"?>
<!DOCTYPE product SYSTEM "product.dtd">
<product>
    <id>P-100</id>
    <name>Keyboard</name>
</product>
~~~

Nếu `product.dtd` nằm trong repository, có thể cung cấp nó cho parser bằng đường dẫn tương đối hoặc ánh xạ qua XMLCatalog. Cách dùng catalog được trình bày ở phần sau; ưu điểm là nhiều file XML có thể cùng tham chiếu một DTD bằng định danh ổn định.

### 2.2. Kiểm tra XML Schema (XSD)

DTD phù hợp với nhiều tài liệu XML cũ và cấu trúc cơ bản. Với XSD, schema thường được tham chiếu bằng thuộc tính `xsi:schemaLocation` hoặc `xsi:noNamespaceSchemaLocation`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<product xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:noNamespaceSchemaLocation="product.xsd">
    <id>P-100</id>
    <name>Keyboard</name>
    <price>49.90</price>
</product>
~~~

Việc kiểm tra XSD phụ thuộc parser và các feature/property mà parser hỗ trợ. Với parser Xerces, có thể cấu hình validation và XML Schema validation thông qua các thuộc tính SAX:

~~~xml
<target name="validate-xsd">
    <xmlvalidate file="src/xml/product.xml"
                 failonerror="true"
                 warn="true">
        <attribute name="http://xml.org/sax/features/validation"
                   value="true"/>
        <attribute name="http://apache.org/xml/features/validation/schema"
                   value="true"/>
    </xmlvalidate>
</target>
~~~

Các URI feature trên là cấu hình đặc thù của parser Xerces phổ biến; parser khác có thể không hỗ trợ hoặc dùng cơ chế khác. Nếu parser không nhận feature, task có thể báo lỗi cấu hình. Hãy chọn parser có hỗ trợ XSD, xác định rõ phiên bản parser trong môi trường build và kiểm tra kết quả validation trên CI. XMLCatalog có thể giúp parser phân giải tài nguyên ngoài theo các định danh mà nó hỗ trợ, nhưng bản thân catalog không bật schema validation.

## 3. Biến đổi XML bằng `<xslt>`

Task `<xslt>` sử dụng stylesheet XSLT để chuyển tài liệu XML đầu vào thành một dạng đầu ra khác. XSLT thường được dùng để tạo HTML, tài liệu hướng dẫn, báo cáo, XML đã chuẩn hóa hoặc các file trung gian phục vụ bước đóng gói.

Một stylesheet XSLT đơn giản:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

    <xsl:output method="html" encoding="UTF-8" indent="yes"/>

    <xsl:template match="/">
        <html>
            <head><title>Product</title></head>
            <body>
                <h1><xsl:value-of select="product/name"/></h1>
                <p>ID: <xsl:value-of select="product/id"/></p>
                <p>Price: <xsl:value-of select="product/price"/></p>
            </body>
        </html>
    </xsl:template>

</xsl:stylesheet>
~~~

Giả sử file được lưu tại `src/xsl/product-to-html.xsl`. Có thể dùng task Ant để biến đổi một XML:

~~~xml
<target name="transform-product">
    <mkdir dir="build/html"/>
    <xslt in="src/xml/product.xml"
          out="build/html/product.html"
          style="src/xsl/product-to-html.xsl"/>
</target>
~~~

- `in`: file XML đầu vào trong chế độ một file.
- `out`: file kết quả.
- `style`: stylesheet XSLT được sử dụng.

Ant gọi bộ xử lý XSLT thông qua các API Java XML phù hợp. Bộ xử lý cụ thể phụ thuộc JAXP provider/processor và cấu hình classpath của build. Vì vậy, cùng một stylesheet có thể có khác biệt về tính năng nếu môi trường local và CI dùng processor hoặc phiên bản khác nhau.

### 3.1. Biến đổi nhiều file theo cây thư mục

Khi có nhiều XML cùng dùng một stylesheet, có thể dùng chế độ thư mục:

~~~xml
<target name="transform-all">
    <xslt basedir="src/xml"
          destdir="build/html"
          includes="**/*.xml"
          excludes="**/draft/**"
          style="src/xsl/document-to-html.xsl"
          extension=".html"/>
</target>
~~~

Trong chế độ này:

- `basedir` là thư mục chứa XML nguồn.
- `destdir` là thư mục nhận kết quả.
- `includes` và `excludes` chọn tập XML cần biến đổi.
- `style` chỉ định stylesheet dùng chung.
- `extension` chỉ định phần mở rộng của file kết quả.

Ant giữ cấu trúc đường dẫn tương đối khi tạo output. Ví dụ `src/xml/api/guide.xml` có thể tạo thành `build/html/api/guide.html`. Điều này hữu ích khi tài liệu có nhiều nhóm hoặc package thư mục.

Khi dùng `basedir` và `destdir`, cần xác định rõ base directory và nơi stylesheet được phân giải. Để build dễ di chuyển, có thể khai báo property `location` cho thư mục source, output và stylesheet, rồi dùng các property đó trong target.

~~~xml
<property name="xml.src.dir" location="src/xml"/>
<property name="html.dir" location="build/html"/>
<property name="xsl.file" location="src/xsl/document-to-html.xsl"/>

<target name="transform-docs">
    <mkdir dir="${html.dir}"/>
    <xslt basedir="${xml.src.dir}"
          destdir="${html.dir}"
          style="${xsl.file}"
          includes="**/*.xml"
          extension=".html"/>
</target>
~~~

### 3.2. Truyền tham số vào stylesheet

Một stylesheet có thể khai báo tham số bằng `<xsl:param>`. Ant truyền giá trị qua nested element `<param>`:

Trong stylesheet:

~~~xml
<xsl:param name="siteTitle" select="'Documentation'"/>
~~~

Trong build file:

~~~xml
<xslt in="src/xml/index.xml"
      out="build/html/index.html"
      style="src/xsl/document-to-html.xsl">
    <param name="siteTitle" expression="Product Documentation"/>
</xslt>
~~~

`name` phải khớp với tên tham số trong stylesheet. `expression` là giá trị Ant truyền cho tham số XSLT; nó không phải biểu thức shell. Có thể dùng property của Ant để cung cấp giá trị:

~~~xml
<property name="site.title" value="Product Documentation"/>

<xslt in="src/xml/index.xml"
      out="build/html/index.html"
      style="src/xsl/document-to-html.xsl">
    <param name="siteTitle" expression="${site.title}"/>
</xslt>
~~~

Nhờ vậy, cùng stylesheet có thể được tái sử dụng cho nhiều môi trường hoặc phiên bản tài liệu mà không phải sửa nội dung XSLT.

### 3.3. Cấu hình output property

Có thể truyền các thuộc tính đầu ra của transformer bằng nested `<outputproperty>`:

~~~xml
<xslt in="src/xml/index.xml"
      out="build/html/index.html"
      style="src/xsl/document-to-html.xsl">
    <outputproperty name="indent" value="yes"/>
    <outputproperty name="encoding" value="UTF-8"/>
</xslt>
~~~

Các output property phải được processor hỗ trợ. Một số thiết lập cũng có thể được khai báo trực tiếp bằng `<xsl:output>` trong stylesheet. Khi cần kết quả nhất quán giữa các môi trường, nên chọn một nơi làm nguồn cấu hình chính và kiểm tra output thực tế.

## 4. XMLCatalog là gì?

XMLCatalog là một data type của Ant dùng để ánh xạ định danh tài nguyên XML sang vị trí khác, thường là file cục bộ. Nó đặc biệt hữu ích khi XML sử dụng DTD hoặc external entity được nhận diện bởi PUBLIC ID hoặc SYSTEM ID.

Nếu XML tham chiếu DTD bằng URL, parser có thể cố truy cập mạng mỗi lần validate hoặc transform. Điều đó làm build phụ thuộc vào kết nối Internet, máy chủ ngoài và trạng thái dịch vụ. XMLCatalog cho phép ánh xạ định danh đó tới file đã lưu trong repository hoặc một thư mục dependency đã được quản lý.

Ví dụ khai báo catalog:

~~~xml
<xmlcatalog id="project.catalog">
    <dtd publicId="-//ACME//DTD PRODUCT 1.0//EN"
         location="schema/product.dtd"/>
    <entity publicId="urn:acme:common-entities"
            location="schema/common.ent"/>
</xmlcatalog>
~~~

Trong đó:

- `id` đặt tên reference cho catalog để task khác tái sử dụng.
- `<dtd>` ánh xạ public identifier của DTD tới file cục bộ.
- `<entity>` ánh xạ external entity tới file cục bộ.
- `location` là đường dẫn hoặc vị trí tài nguyên được dùng khi resolve.

XML có thể khai báo PUBLIC ID tương ứng:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE product PUBLIC "-//ACME//DTD PRODUCT 1.0//EN"
                        "https://schemas.example.invalid/product.dtd">
<product>
    <id>P-100</id>
    <name>Keyboard</name>
</product>
~~~

Khi parser yêu cầu DTD, catalog có thể ánh xạ PUBLIC ID `-//ACME//DTD PRODUCT 1.0//EN` tới `schema/product.dtd`. Build không cần tải DTD từ URL trong tài liệu.

### 4.1. Dùng catalog trong `<xmlvalidate>`

Catalog có thể được lồng vào task validation:

~~~xml
<xmlcatalog id="project.catalog">
    <dtd publicId="-//ACME//DTD PRODUCT 1.0//EN"
         location="schema/product.dtd"/>
</xmlcatalog>

<target name="validate-xml">
    <xmlvalidate failonerror="true" warn="true">
        <fileset dir="src/xml">
            <include name="**/*.xml"/>
        </fileset>
        <xmlcatalog refid="project.catalog"/>
    </xmlvalidate>
</target>
~~~

Task `<xmlvalidate>` dùng catalog khi parser cần resolve DTD hoặc entity. Nếu không có ánh xạ phù hợp, parser có thể thử xử lý SYSTEM ID theo cách thông thường, tùy parser và cấu hình bảo mật.

### 4.2. Dùng catalog trong `<xslt>`

XSLT task cũng có thể nhận XMLCatalog để phân giải tài nguyên XML ngoài trong quá trình đọc đầu vào hoặc xử lý stylesheet:

~~~xml
<target name="transform-xml">
    <xslt in="src/xml/product.xml"
          out="build/html/product.html"
          style="src/xsl/product-to-html.xsl">
        <xmlcatalog refid="project.catalog"/>
    </xslt>
</target>
~~~

Nếu stylesheet hoặc XML sử dụng DTD/entity, catalog giúp processor tìm tài nguyên theo ánh xạ được cung cấp. Phạm vi URI được resolver xử lý phụ thuộc parser/transformer và cách tài nguyên được tham chiếu; hãy kiểm tra log nếu một stylesheet import/include hoặc một external resource không được resolve như mong đợi.

### 4.3. Catalog có thể được chia sẻ qua nhiều task

Khai báo catalog ở cấp project với `id` giúp validate và transform dùng cùng một nguồn ánh xạ:

~~~xml
<xmlcatalog id="project.catalog">
    <dtd publicId="-//ACME//DTD PRODUCT 1.0//EN"
         location="schema/product.dtd"/>
    <entity publicId="urn:acme:common-entities"
            location="schema/common.ent"/>
</xmlcatalog>

<target name="validate-xml">
    <xmlvalidate file="src/xml/product.xml" failonerror="true">
        <xmlcatalog refid="project.catalog"/>
    </xmlvalidate>
</target>

<target name="transform-xml" depends="validate-xml">
    <xslt in="src/xml/product.xml"
          out="build/html/product.html"
          style="src/xsl/product-to-html.xsl">
        <xmlcatalog refid="project.catalog"/>
    </xslt>
</target>
~~~

Cùng một reference `project.catalog` được dùng tại hai vị trí. Khi thêm DTD hoặc entity mới, chỉ cần cập nhật catalog chung thay vì lặp lại ánh xạ trong từng task.

## 5. Kết hợp validate và transform trong một pipeline

Một build file có thể gom các property, catalog và target theo từng trách nhiệm:

~~~xml
<project name="xml-pipeline" default="build-docs">

    <property name="xml.src.dir" location="src/xml"/>
    <property name="xsl.file" location="src/xsl/document-to-html.xsl"/>
    <property name="html.dir" location="build/html"/>

    <xmlcatalog id="project.catalog">
        <dtd publicId="-//ACME//DTD PRODUCT 1.0//EN"
             location="schema/product.dtd"/>
    </xmlcatalog>

    <target name="validate-xml">
        <xmlvalidate failonerror="true" warn="true">
            <fileset dir="${xml.src.dir}">
                <include name="**/*.xml"/>
                <exclude name="**/draft/**"/>
            </fileset>
            <xmlcatalog refid="project.catalog"/>
        </xmlvalidate>
    </target>

    <target name="transform-xml" depends="validate-xml">
        <mkdir dir="${html.dir}"/>
        <xslt basedir="${xml.src.dir}"
              destdir="${html.dir}"
              style="${xsl.file}"
              includes="**/*.xml"
              excludes="**/draft/**"
              extension=".html">
            <xmlcatalog refid="project.catalog"/>
            <param name="siteTitle" expression="Product Documentation"/>
        </xslt>
    </target>

    <target name="build-docs" depends="transform-xml"/>

</project>
~~~

Khi gọi `ant build-docs`, Ant xử lý `validate-xml` trước, sau đó mới tới `transform-xml`. Nếu validation thất bại với `failonerror="true"`, target validation thất bại và pipeline không tiếp tục transform.

Hai target dùng cùng pattern include/exclude để tránh tình huống validate một tập file nhưng lại transform một tập khác. Nếu có yêu cầu transform các file không cần validation hoặc validation theo schema khác nhau, hãy định nghĩa tập file và target riêng thay vì dùng chung một pattern thiếu chủ đích.

## 6. Kiểm soát bộ xử lý XSLT và parser XML

Ant gọi parser và transformer thông qua các thư viện Java. Kết quả có thể phụ thuộc vào provider được tìm thấy trên classpath, phiên bản JDK và thư viện XML bổ sung.

Một số lưu ý:

- `<xmlvalidate>` có thể dùng parser mặc định của JVM hoặc parser được cấu hình qua `classname` và classpath.
- `<xslt>` sử dụng cơ chế JAXP để tìm transformer; processor cụ thể phụ thuộc provider và cấu hình task.
- Một số tính năng XSLT mới hơn không được hỗ trợ bởi processor cũ.
- Các parser có thể hỗ trợ khác nhau về DTD, XSD, external entity và các tính năng bảo mật.
- Máy local và CI nên dùng cùng phiên bản JDK, parser và XSLT provider nếu cần kết quả giống nhau.

Khi dự án cần một processor cụ thể, hãy khai báo thư viện đó trong build environment và cấu hình task theo hướng dẫn của phiên bản Ant đang sử dụng. Tránh phụ thuộc ngầm vào thư viện tình cờ có trong JDK hoặc trên máy cá nhân.

## 7. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra hoặc xử lý |
|---|---|---|
| XML không well-formed | Thiếu root, sai thẻ, ký tự đặc biệt chưa escape | Đọc dòng/cột parser báo; sửa cú pháp XML |
| XML không hợp lệ theo DTD | Thiếu element/attribute bắt buộc hoặc sai thứ tự | Kiểm tra DTD và nội dung XML |
| Không tìm thấy DTD | SYSTEM/PUBLIC ID chưa được map hoặc đường dẫn sai | Kiểm tra XMLCatalog và `location` |
| Build cố truy cập Internet để lấy DTD | Catalog không có mapping phù hợp hoặc resolver không được gắn vào task | Thêm catalog entry đúng định danh; kiểm tra parser log |
| XSD không được kiểm tra | Parser chưa bật schema validation hoặc không hỗ trợ feature | Cấu hình parser XSD phù hợp và kiểm tra provider |
| `xslt` không tìm thấy stylesheet | Sai đường dẫn `style` hoặc working/base directory | In property đường dẫn và kiểm tra file tồn tại |
| Không tạo được output | Sai `destdir`, quyền ghi hoặc lỗi transformer | Tạo thư mục đích, kiểm tra quyền và log |
| Tham số XSLT không có tác dụng | Tên `<param>` không trùng `<xsl:param>` | Kiểm tra chính tả và kiểu giá trị truyền vào |
| Local chạy nhưng CI thất bại | Khác JDK, parser hoặc XSLT provider | Ghi log phiên bản môi trường và pin dependency |
| Stylesheet import/include không được resolve | URI trong stylesheet không phù hợp với base URI hoặc resolver | Kiểm tra URI và khả năng resolve của processor/catalog |

## 8. Lưu ý về bảo mật khi xử lý XML

XML có thể tham chiếu external entity hoặc DTD. Parser được cấu hình cho phép tải tài nguyên ngoài có thể truy cập file hoặc dịch vụ mạng mà build không dự kiến. Trong pipeline xử lý XML từ nguồn không tin cậy, cần xem xét cấu hình parser để hạn chế external entity và external DTD theo chính sách bảo mật.

XMLCatalog giúp chuyển các định danh đã biết tới tài nguyên cục bộ, nhưng không tự động biến mọi XML thành an toàn. Nó cũng không thay thế cấu hình parser chống XXE (XML External Entity), kiểm soát nguồn đầu vào hoặc kiểm tra nội dung stylesheet. Chỉ cho phép những DTD/entity cần thiết; không mở rộng quyền truy cập tài nguyên ngoài nếu không có lý do rõ ràng.

Đối với tài liệu nội bộ, lưu DTD/XSD và stylesheet trong repository hoặc dependency được quản lý giúp build ổn định hơn. Nếu tài liệu đầu vào đến từ người dùng hoặc hệ thống bên ngoài, cần giới hạn loại tài nguyên mà parser được phép resolve và kiểm tra nội dung trước khi đưa vào pipeline.

## 9. Cách tổ chức thư mục cho dự án XML

Một cấu trúc đơn giản có thể như sau:

~~~text
project/
├── build.xml
├── src/
│   └── xml/
│       ├── product.xml
│       └── catalog.xml
├── schema/
│   ├── product.dtd
│   └── common.ent
├── xsl/
│   └── product-to-html.xsl
└── build/
    └── html/
~~~

- `src/xml`: tài liệu XML đầu vào.
- `schema`: DTD, XSD hoặc entity cục bộ.
- `xsl`: stylesheet XSLT.
- `build/html`: kết quả transform, thường là output có thể tái tạo và có thể xóa khi clean.

Các đường dẫn nên được khai báo bằng property `location` để dễ thay đổi base directory và tránh lặp literal trong nhiều target. Không nên ghi output transform vào thư mục source vì có thể khiến lần chạy sau vô tình xử lý output như input.

## 10. Quy trình debug

Khi validation hoặc transform thất bại, nên tách chẩn đoán theo từng lớp:

1. Xác nhận XML đầu vào tồn tại và FileSet có chọn đúng file.
2. Chạy riêng target `validate-xml` để biết lỗi cú pháp, DTD hoặc schema.
3. Kiểm tra PUBLIC ID/SYSTEM ID trong XML và mapping tương ứng trong catalog.
4. Xác nhận parser có hỗ trợ DTD/XSD và các feature đang cấu hình.
5. Chạy riêng target `transform-xml` với một XML và stylesheet đơn giản.
6. Kiểm tra các tham số XSLT, output property, URI import/include và thư mục đích.
7. So sánh phiên bản JDK, parser và XSLT provider giữa local và CI.

Có thể bật log chi tiết khi chạy Ant:

~~~bash
ant -verbose validate-xml
ant -debug transform-xml
~~~

Log chi tiết giúp xác định task nào chạy, file nào được chọn và vị trí lỗi parser/transformer. Với tập XML lớn, nên thử một file đại diện trước khi chạy toàn bộ cây thư mục.

## Kết luận

`<xmlvalidate>` kiểm tra XML trước khi xử lý; `<xslt>` biến đổi XML theo stylesheet; `<xmlcatalog>` cung cấp ánh xạ định danh tới DTD/entity hoặc tài nguyên XML phù hợp. Kết hợp chúng trong pipeline `validate -> transform` giúp build dừng khi dữ liệu đầu vào sai, tái sử dụng schema/catalog và tạo đầu ra nhất quán. Hãy quản lý parser và XSLT provider rõ ràng, dùng catalog cục bộ để giảm phụ thuộc mạng, và cấu hình bảo mật XML phù hợp với mức độ tin cậy của dữ liệu đầu vào.
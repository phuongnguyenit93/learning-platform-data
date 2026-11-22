# Kiểm soát XML bên ngoài và sử dụng catalog khi cần trong Apache Ant

## 1. Vì sao XML bên ngoài ảnh hưởng đến an toàn build?

Một dự án dùng **Apache Ant** thường có nhiều tệp XML: `build.xml`, cấu hình kiểm thử, mô tả tài liệu, cấu hình công cụ và dữ liệu đầu vào. Một số tác vụ của Ant và thư viện Java xử lý XML bằng parser hỗ trợ **DOCTYPE, DTD, entity ngoài, XML Schema, XInclude hoặc XSLT**. Nếu không đặt giới hạn rõ ràng, parser có thể cố đọc một tài nguyên ngoài tài liệu chính:

- Một URL trên Internet, khiến build phụ thuộc vào mạng hoặc nội dung của máy chủ bên ngoài.
- Một địa chỉ nội bộ, khiến quá trình build phát sinh yêu cầu tới dịch vụ mà tài liệu XML bình thường không được quyền truy cập.
- Một tệp trên máy chạy CI, dẫn tới nguy cơ làm lộ dữ liệu hoặc đọc nội dung ngoài phạm vi dự kiến.
- Một DTD/schema được cập nhật âm thầm, làm hai lần build từ cùng commit có kết quả khác nhau.
- Một chuỗi entity lồng nhau tiêu thụ nhiều CPU và bộ nhớ, gây từ chối dịch vụ với parser.

Rủi ro thường được nhắc đến dưới tên **XML External Entity (XXE)**, nhưng an toàn XML còn bao gồm tải schema từ xa, `xsl:include`/`xsl:import`, hàm `document()` trong XSLT và các giới hạn tài nguyên của parser. Không phải mọi cơ chế tham chiếu ngoài đều dùng chung một bộ resolver.

Bài này trình bày cách nhận diện nguồn XML, thiết lập chính sách truy cập phù hợp, dùng **XML Catalog** để ánh xạ một DTD đã được phê duyệt sang bản cục bộ, và kiểm tra rằng pipeline CI/CD không bất ngờ gọi mạng hoặc đọc tài nguyên bị cấm.

**Nguyên tắc xuyên suốt:** tài liệu XML và cấu hình build cần được xử lý theo **mức độ tin cậy của đầu vào**. Catalog giúp kiểm soát nơi lấy tài nguyên được phép sử dụng; catalog **không phải** cơ chế bảo mật thay thế việc vô hiệu hóa các khả năng nguy hiểm của parser và cô lập môi trường build.

## 2. Phân biệt XML do dự án quản lý và XML không đáng tin cậy

Không thể áp dụng một cấu hình duy nhất cho mọi tài liệu. Cần phân loại đầu vào trước khi chọn parser và chính sách tải tài nguyên.

| Loại XML | Ví dụ | Chính sách gợi ý |
| --- | --- | --- |
| Cấu hình Ant do nhóm duy trì | `build.xml` trong repository đã review | Tránh DOCTYPE và tham chiếu ngoài không cần thiết; chỉ chạy build script từ nguồn tin cậy. |
| XML tài liệu cần DTD cố định | DocBook hoặc tài liệu nội bộ có khai báo DTD | Cho phép đúng DTD phiên bản đã duyệt qua catalog cục bộ; chặn truy cập ngoài dự kiến. |
| XML đầu vào từ người dùng, PR hoặc đối tác | File cấu hình import, dữ liệu XML do bên ngoài gửi | Mặc định **không cho phép DOCTYPE/entity ngoài**; parse bằng cấu hình an toàn và giới hạn tài nguyên. |
| XML cần kiểm tra XSD | `schemaLocation` trỏ tới XSD | Cố định schema và các `include/import`; đặt giới hạn truy cập ngoài của schema validator. |
| XSLT hoặc XML dùng để biến đổi | `style.xsl`, `input.xml` | Kiểm soát cả nguồn XML, stylesheet, `document()`, `xsl:import` và extension functions. |

**Điểm dễ nhầm:** nếu tệp `build.xml` do đối tượng không tin cậy chỉnh sửa được, họ có thể thêm task `<exec>`, `<delete>` hoặc các task khác. XML Catalog không làm một build script không tin cậy trở nên an toàn. Phải dùng kiểm soát quyền sửa repository, review và cô lập runner; chính sách XML parser chỉ giải quyết một phần bề mặt tấn công.

### Ví dụ tham chiếu XML bên ngoài

Tài liệu sau yêu cầu parser tìm DTD ở một URL:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE manual PUBLIC
    "-//EXAMPLE//DTD Manual 1.0//EN"
    "https://schemas.example.invalid/manual.dtd">
<manual>
    <title>Hướng dẫn build</title>
    <paragraph>Không phụ thuộc mạng khi xác minh.</paragraph>
</manual>
```

Trong ví dụ, `schemas.example.invalid` là địa chỉ minh họa; không có ý định truy cập một server thật. Khi được yêu cầu validate, parser có thể tìm DTD từ URL đó nếu không có resolver/catalog phù hợp hoặc không có biện pháp chặn. Đó là nguồn không xác định đối với CI.

Một kiểu tài liệu khác có thể khai báo entity bên ngoài:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE note [
    <!ENTITY external SYSTEM "file:///path/to/local-resource.txt">
]>
<note>&external;</note>
```

Một parser cho phép external general entity có thể cố lấy nội dung tại đường dẫn đó. Nếu đầu vào không đáng tin, chính sách an toàn cần **từ chối khai báo DOCTYPE/entity ngoài** thay vì cố đoán danh sách URL cần chặn.

## 3. XML Catalog giải quyết vấn đề gì?

**XML Catalog** là cơ chế ánh xạ **định danh của tài nguyên ngoài** sang vị trí đã kiểm soát, thường là tệp có sẵn trong repository hoặc một bộ dependency cố định. Thay vì truy cập DTD qua Internet, parser được cấu hình với catalog có thể tìm bản DTD cục bộ.

Ví dụ:

```text
XML: manual.xml
  |
  +-- PUBLIC "-//EXAMPLE//DTD Manual 1.0//EN"
  |          SYSTEM "https://schemas.example.invalid/manual.dtd"
  |
  v
XML resolver + catalog cục bộ
  |
  +-- PUBLIC ID khớp mục catalog?
             |
             +-- Có --> schemas/manual.dtd (phiên bản đã duyệt)
             |
             +-- Không --> phải áp dụng chính sách từ chối
                          hoặc xử lý lỗi có kiểm soát
```

Với Apache Ant, cấu trúc dữ liệu **`<xmlcatalog>`** có thể được khai báo để hỗ trợ việc phân giải entity/DTD của các task XML tương thích. Một số task, chẳng hạn `<xmlvalidate>`, cho phép gắn catalog. Các task khác và các trình xử lý XML bên trong chương trình do Ant chạy có thể **không sử dụng catalog này**; cần xem khả năng hỗ trợ thực tế của từng task.

### Catalog không có nghĩa là “cấm Internet”

Một catalog chỉ có mục ánh xạ cho định danh đã biết. Khi không có mục phù hợp, một resolver thông thường có thể chuyển cho cơ chế mặc định của parser, dẫn tới truy cập mạng hoặc filesystem. Do vậy:

- Không xem việc đã khai báo `<xmlcatalog>` là bằng chứng tất cả entity ngoài đã bị vô hiệu hóa.
- Không dùng catalog để “cho phép mọi URL rồi ánh xạ nếu thấy phù hợp”.
- Không để fallback âm thầm tải DTD/schema mới từ nơi khác trong một build cần kiểm soát đầu vào.
- Kiểm tra riêng các cơ chế tham chiếu khác như XSD import và XSLT import; mục ánh xạ DTD không tự chặn chúng.

Catalog hợp lý khi dự án **thật sự cần** DTD/schema đã được duyệt. Nếu XML không cần DOCTYPE, lựa chọn đơn giản và an toàn hơn là **không sử dụng DOCTYPE** và cấu hình parser từ chối nó.

## 4. Dự án Ant mẫu: xác minh DTD bằng catalog cục bộ

Giả sử tài liệu được quản lý trong repository và bắt buộc validate theo một DTD cụ thể:

```text
ant-xml-safe/
├── build.xml
├── docs/
│   └── manual.xml
└── schemas/
    └── manual.dtd
```

### 4.1. Tệp DTD đã được duyệt

Tạo `schemas/manual.dtd`:

```dtd
<!ELEMENT manual (title, paragraph+)>
<!ELEMENT title (#PCDATA)>
<!ELEMENT paragraph (#PCDATA)>
```

Đây là DTD đơn giản, không tham chiếu tài nguyên khác. Trong thực tế, hãy đưa DTD đúng phiên bản được phê duyệt vào nguồn quản lý và ghi nhận checksum; không tải bản mới rồi thay thế âm thầm trong pipeline.

### 4.2. XML dùng định danh PUBLIC cố định

Tạo `docs/manual.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE manual PUBLIC
    "-//EXAMPLE//DTD Manual 1.0//EN"
    "https://schemas.example.invalid/manual.dtd">
<manual>
    <title>Tài liệu Ant</title>
    <paragraph>Validate bằng DTD được lưu tại chỗ.</paragraph>
</manual>
```

Tên trong `PUBLIC` là **public identifier** được catalog nhận diện. URL trong `SYSTEM` chỉ còn là định danh tham chiếu trong ví dụ khi resolver thực sự áp dụng ánh xạ; tài liệu không cần dựa vào máy chủ từ xa để lấy DTD.

### 4.3. Khai báo catalog trong `build.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-xml-safe" default="validate-docs" basedir=".">

    <property name="docs.dir" location="docs"/>
    <property name="schemas.dir" location="schemas"/>

    <xmlcatalog id="approved.dtd.catalog">
        <dtd publicId="-//EXAMPLE//DTD Manual 1.0//EN"
             location="${schemas.dir}/manual.dtd"/>
    </xmlcatalog>

    <target name="validate-docs">
        <xmlvalidate file="${docs.dir}/manual.xml"
                     lenient="false"
                     failonerror="true">
            <xmlcatalog refid="approved.dtd.catalog"/>
        </xmlvalidate>
    </target>

</project>
```

Chạy tại thư mục dự án:

```bash
ant -f build.xml validate-docs
```

Vai trò của từng phần:

1. `location` của property định vị thư mục so với `basedir`, giúp catalog không phụ thuộc thư mục làm việc hiện tại của terminal.
2. `<xmlcatalog id="...">` định nghĩa bộ ánh xạ có thể được tham chiếu lại.
3. `<dtd publicId="..." location="..."/>` nối **đúng public identifier** sang file cục bộ do dự án quản lý.
4. `<xmlvalidate lenient="false">` yêu cầu kiểm tra hợp lệ theo DTD. `failonerror="true"` làm build dừng khi validation báo lỗi.
5. `<xmlcatalog refid="..."/>` truyền catalog cho task `xmlvalidate` thay vì để nó phải tìm DTD từ nguồn chưa được kiểm soát.

Với DTD ở ví dụ, `<manual>` có một `<title>` và ít nhất một `<paragraph>`. Nếu loại bỏ `<title>`, việc validate theo DTD sẽ thất bại. Đây là khác biệt giữa **well-formed XML** (cú pháp XML hợp lệ) và **valid XML** (thỏa mãn DTD/schema đã chọn).

> **Giới hạn bảo mật của ví dụ:** đây là cấu hình sử dụng DTD nội bộ với XML đã được duyệt. Một `PUBLIC ID` lạ, entity ngoài khác hoặc parser không dùng catalog vẫn có thể đi tới cơ chế resolver mặc định. Muốn đảm bảo không có truy cập ngoài danh sách cho phép, cần bổ sung giới hạn parser và môi trường, đồng thời chứng minh tác dụng bằng thử nghiệm trong CI.

### 4.4. Khi nào ánh xạ không hoạt động?

Có vài trường hợp thường gặp:

- File XML không còn `PUBLIC`, chỉ khai báo `SYSTEM`: mục `<dtd publicId="...">` trong ví dụ không khớp.
- Public identifier thay đổi cách viết: catalog không còn ánh xạ đúng resource cần tìm.
- DTD có thêm entity parameter hoặc DTD con tham chiếu tài nguyên khác: ánh xạ một DTD cấp đầu chưa chắc bao phủ toàn bộ cây phụ thuộc.
- Task dùng parser/resolver riêng và không nhận catalog mà ta đã định nghĩa.
- File DTD bị thiếu trên runner CI hoặc đường dẫn dựa trên working directory sai.
- Tên, phiên bản hoặc checksum của DTD cục bộ bị thay đổi nhưng chưa được review.

Với tài liệu có nhiều DTD hoặc định danh `SYSTEM`, hãy xây danh mục ánh xạ rõ ràng cho **mọi định danh cần thiết** bằng khả năng catalog mà công cụ thực tế hỗ trợ (chẳng hạn chuẩn OASIS XML Catalog khi có resolver phù hợp). Không suy đoán rằng một mục ánh xạ `PUBLIC` bao phủ mọi URL có tên gần giống.

## 5. Quyết định an toàn quan trọng: từ chối DOCTYPE cho XML không đáng tin cậy

Nếu một pipeline nhận XML do bên ngoài gửi và chỉ cần đọc dữ liệu, nó thường **không cần DTD**. Cấu hình phù hợp là từ chối hoàn toàn DOCTYPE và entity ngoài.

Một parser Java dùng JAXP có thể cấu hình theo hướng:

- Từ chối khai báo `DOCTYPE` (ví dụ feature `http://apache.org/xml/features/disallow-doctype-decl` trên parser hỗ trợ Xerces).
- Vô hiệu hóa external general entities và external parameter entities.
- Ngăn tải external DTD khi không validate.
- Tắt XInclude nếu không có nhu cầu.
- Đặt giới hạn xử lý entity và kích thước/tài nguyên.
- Xem việc parser **không hỗ trợ** cờ bảo mật bắt buộc là lỗi cấu hình, không âm thầm bỏ qua.

Các tên feature ở trên phụ thuộc parser. Không có một tập tên feature riêng của Ant được đảm bảo hoạt động giống hệt trên mọi bộ phân tích XML. Những JAXP parser hoặc task Ant khác nhau có thể hỗ trợ cách cấu hình khác nhau.

### Ví dụ trình kiểm tra XML không đáng tin cậy bằng Java

Nếu task hiện có không cung cấp cách xác nhận parser đã bật đúng cờ, một helper Java chạy trong CI có thể thực hiện policy rõ ràng. Đặt tại `ci/src/SecureXmlCheck.java`:

```java
import java.io.File;
import javax.xml.parsers.SAXParserFactory;
import org.xml.sax.helpers.DefaultHandler;

public final class SecureXmlCheck {
    private SecureXmlCheck() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Usage: SecureXmlCheck XML_FILE");
        }

        SAXParserFactory factory = SAXParserFactory.newInstance();
        factory.setNamespaceAware(true);
        factory.setValidating(false);
        factory.setXIncludeAware(false);

        // Parser không hỗ trợ feature bắt buộc sẽ ném exception:
        // build fail thay vì bỏ qua chính sách bảo vệ.
        factory.setFeature(
            "http://apache.org/xml/features/disallow-doctype-decl",
            true);
        factory.setFeature(
            "http://xml.org/sax/features/external-general-entities",
            false);
        factory.setFeature(
            "http://xml.org/sax/features/external-parameter-entities",
            false);
        factory.setFeature(
            "http://apache.org/xml/features/nonvalidating/load-external-dtd",
            false);

        factory.newSAXParser().parse(
            new File(args[0]), new DefaultHandler());

        System.out.println("XML input accepted");
    }
}
```

Và tích hợp với Ant:

```xml
<property name="ci.classes.dir" location="build/ci-classes"/>

<target name="compile-xml-check">
    <mkdir dir="${ci.classes.dir}"/>
    <javac srcdir="ci/src"
           destdir="${ci.classes.dir}"
           includeantruntime="false"
           encoding="UTF-8"
           release="17"/>
</target>

<target name="check-untrusted-xml" depends="compile-xml-check">
    <fail unless="xml.input"
          message="Thiếu -Dxml.input=đường-dẫn-file-xml"/>

    <java classname="SecureXmlCheck"
          fork="true"
          failonerror="true">
        <classpath>
            <pathelement location="${ci.classes.dir}"/>
        </classpath>
        <arg file="${xml.input}"/>
    </java>
</target>
```

Ví dụ yêu cầu JDK 17+ và Ant có hỗ trợ `release` của `<javac>`. Gọi:

```bash
ant check-untrusted-xml "-Dxml.input=docs/untrusted.xml"
```

Nếu file có DOCTYPE, parser phù hợp với các feature trên sẽ từ chối. Nếu factory không hỗ trợ feature bắt buộc, chương trình dừng với exception, và `failonerror="true"` làm target Ant thất bại. Cách này mang tính **fail closed** đối với chính sách đã khai báo.

Trình kiểm tra chỉ đảm bảo chính lần parse do helper thực hiện. Nếu một target khác sau đó mở lại file XML bằng parser thiếu bảo vệ, rủi ro vẫn tồn tại. **Mọi nơi thực sự tiêu thụ dữ liệu không đáng tin cậy đều phải được cấu hình an toàn**; không thể dựa vào một lần “scan” rồi cho parser khác tự động tin file đó.

### Phân biệt parser không hỗ trợ feature với file XML sai

- Parser không nhận feature bắt buộc: lỗi cấu hình/toolchain; cần chọn parser hoặc cách parse hỗ trợ.
- XML có `DOCTYPE`: bị từ chối đúng theo policy của đầu vào không đáng tin.
- XML malformed: lỗi cú pháp dữ liệu; build dừng theo yêu cầu.
- XML well-formed không có DOCTYPE: được phép qua bước kiểm tra cú pháp; các quy tắc nội dung riêng vẫn phải validate theo schema/data contract khi cần.

Việc từ chối DOCTYPE không tự bảo đảm dữ liệu XML là an toàn cho mọi bước xử lý sau đó (ví dụ nội dung văn bản có thể chứa dữ liệu nguy hiểm cho SQL, shell hoặc HTML nếu ứng dụng dùng sai cách). Đó là các lớp kiểm soát khác.

## 6. Giới hạn truy cập ngoài ở cấp JAXP/JVM

JDK cung cấp các thuộc tính **JAXP External Access Properties** giúp giới hạn giao thức mà parser/transformer được phép dùng để lấy tài nguyên ngoài:

| Thuộc tính hệ thống | Phạm vi thường liên quan | Giá trị trống `""` |
| --- | --- | --- |
| `javax.xml.accessExternalDTD` | External DTD và external entity của parser tương thích | Không cho phép giao thức truy cập ngoài qua cơ chế bị ràng buộc |
| `javax.xml.accessExternalSchema` | Tài nguyên schema mà schema validator lấy thêm | Không cho phép truy cập ngoài qua cơ chế bị ràng buộc |
| `javax.xml.accessExternalStylesheet` | Stylesheet import/include và nguồn ngoài của transformer tương thích | Không cho phép truy cập ngoài qua cơ chế bị ràng buộc |

Trong một quy trình **không cần tài nguyên XML ngoài**, cấu hình JVM của tiến trình Ant có thể đưa các thuộc tính về chuỗi trống. Ví dụ Bash:

```bash
export ANT_OPTS="-Djavax.xml.accessExternalDTD= -Djavax.xml.accessExternalSchema= -Djavax.xml.accessExternalStylesheet="
ant -f build.xml check-untrusted-xml "-Dxml.input=docs/untrusted.xml"
```

Trên PowerShell:

```powershell
$env:ANT_OPTS = '-Djavax.xml.accessExternalDTD= -Djavax.xml.accessExternalSchema= -Djavax.xml.accessExternalStylesheet='
ant -f build.xml check-untrusted-xml '-Dxml.input=docs/untrusted.xml'
```

`ANT_OPTS` là biến Ant launcher thường truyền thành tùy chọn JVM; với bản Ant launcher hoặc runner tùy biến, cần xác nhận các thuộc tính thực sự tới đúng **JVM đang parse XML**. Nếu một task khởi chạy JVM con qua `<java fork="true">` hoặc chương trình ngoài qua `<exec>`, JVM con không đương nhiên nhận mọi system property của JVM cha. Cần truyền thuộc tính riêng, ví dụ:

```xml
<java classname="SecureXmlCheck"
      fork="true"
      failonerror="true">
    <classpath>
        <pathelement location="${ci.classes.dir}"/>
    </classpath>
    <sysproperty key="javax.xml.accessExternalDTD" value=""/>
    <sysproperty key="javax.xml.accessExternalSchema" value=""/>
    <sysproperty key="javax.xml.accessExternalStylesheet" value=""/>
    <arg file="${xml.input}"/>
</java>
```

**Lưu ý về phạm vi bảo vệ:** các thuộc tính truy cập ngoài phụ thuộc vào JAXP parser/transformer và cách resolver được sử dụng. Khi ứng dụng tự cung cấp resolver trả về tài nguyên, một số ràng buộc mặc định của JAXP có thể không áp dụng theo cùng cách. Các thuộc tính này cũng không thay thế việc chặn DOCTYPE khi đầu vào không đáng tin, giới hạn entity expansion, kiểm soát XInclude hoặc sandbox của CI.

Nếu một workflow **thật sự cần** DTD cục bộ qua catalog, chính sách JAXP phải phù hợp với resolver và parser được chọn. Đặt mọi External Access Property về chuỗi trống có thể chặn tài nguyên cần thiết trong một số cấu hình. Không nới toàn bộ sang `all` để sửa lỗi; hãy xác định riêng tài nguyên cần thiết và thiết lập cơ chế cho phép có giới hạn, sau đó kiểm chứng không có truy cập ngoài dự kiến.

## 7. XSD, XSLT và các tham chiếu khác: catalog không bao phủ mặc định

Bên cạnh `<!DOCTYPE>`, XML có thể kéo thêm tài nguyên thông qua nhiều cơ chế.

### 7.1. XSD: `schemaLocation`, `xs:include` và `xs:import`

Ví dụ file XML chỉ định schema ở URL:

```xml
<config xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:noNamespaceSchemaLocation="https://schemas.example.invalid/config.xsd">
    <name>demo</name>
</config>
```

Một validator khi được cấu hình theo schema location có thể cố truy cập URL để lấy XSD. Bản thân việc có thuộc tính `schemaLocation` không đảm bảo mọi parser sẽ tự tìm XSD: cơ chế validate, resolver và cấu hình parser quyết định.

Một XSD đã được tải còn có thể chứa `<xs:include>` hoặc `<xs:import>` trỏ tới XSD khác. Muốn build ổn định, cần kiểm soát **toàn bộ cây schema**, không chỉ file ban đầu. Với Java, có thể cung cấp schema local và sử dụng `LSResourceResolver` hoặc công cụ hỗ trợ catalog cho schema; đồng thời cấu hình chính sách truy cập ngoài cho validator. Không giả định mục `<dtd publicId=...>` trong ví dụ phần 4 tự giải quyết namespace/URI của XSD.

### 7.2. XSLT: stylesheet cũng là đầu vào phải tin cậy

Một stylesheet XSLT có thể dùng:

```xml
<xsl:include href="common.xsl"/>
<xsl:import href="base.xsl"/>
```

hoặc gọi `document()` để nạp XML khác. Những tài nguyên này có thể được resolver của XSLT engine hoặc URI resolver xử lý, không nhất thiết đi qua resolver DTD. Một số XSLT engine còn hỗ trợ extension functions; với stylesheet không đáng tin cậy, cần hạn chế khả năng thực thi code theo engine cụ thể.

Khi dùng task `<xslt>` của Ant:

- Chỉ dùng stylesheet đã review, phiên bản cố định.
- Giữ file `include/import` trong vị trí do repository quản lý.
- Dùng catalog/resolver nếu task và engine được lựa chọn hỗ trợ đúng loại tham chiếu.
- Kiểm soát `javax.xml.accessExternalStylesheet` và những giới hạn tương ứng của transformer.
- Không cho phép stylesheet do bên ngoài gửi chạy với quyền truy cập rộng tới filesystem/mạng của runner.

### 7.3. XInclude và URI trong dữ liệu ứng dụng

XInclude có thể thay thế một phần tài liệu bằng nội dung từ một URL/file khác nếu parser bật hỗ trợ. Chỉ tắt external DTD **không đồng nghĩa** XInclude đã tắt.

Ngoài ra, một thuộc tính XML như `<download url="https://..."/>` chỉ là chuỗi dữ liệu cho đến khi **logic ứng dụng** quyết định tải nó. XML Catalog không can thiệp vào `<get>`, `<exec>`, HTTP client hoặc cơ chế tải riêng của chương trình. Cần kiểm soát ở đúng thành phần thực hiện I/O.

## 8. Ranh giới tin cậy của Ant: build script, task và plugin

Apache Ant có thể được mở rộng bằng `<taskdef>`, `<typedef>`, Antlib và chương trình Java bên ngoài. Mỗi thành phần có thể tự chọn XML parser. Do đó:

1. **Không chạy `build.xml` từ PR không tin cậy với credential triển khai hoặc quyền truy cập nhạy cảm.** Task Ant có thể thực thi chương trình, truy cập file và mạng ngoài việc parse XML.
2. **Giữ phiên bản Ant/JDK/plugin cố định khi cần build tái lập.** Thay đổi parser/JAXP có thể đổi hành vi truy cập tài nguyên ngoài.
3. **Kiểm tra cách task xử lý XML.** `<xmlvalidate>` có hỗ trợ `<xmlcatalog>`, nhưng một task bên thứ ba đọc XML trực tiếp có thể bỏ qua catalog của Ant.
4. **Cấp quyền theo nhu cầu.** Runner cho validation tài liệu không cần secret production, quyền ghi ra ngoài workspace hay mạng nội bộ tùy ý.
5. **Giới hạn thời gian và bộ nhớ** của các bước parse XML không đáng tin. Tắt external entity không giải quyết mọi dạng XML rất lớn hoặc xử lý phức tạp.
6. **Coi catalog và DTD/schema là dependency của build.** Chúng nên có version, review, checksum và chính sách cập nhật giống những tệp build quan trọng khác.

### Truy cập mạng: chính sách phù hợp từng job

Một job CI có thể cần Internet để tải JDK, Ant hoặc thư viện Java, nhưng **bước xác minh XML** có thể chạy trong giai đoạn không cần mạng nếu đã chuẩn bị đủ dependency. Đây là phép thử rõ ràng rằng quá trình validate không còn phụ thuộc tài nguyên ngoài bất ngờ.

Nếu không thể tắt toàn bộ mạng cho job, cân nhắc chia phase: tải dependency đã pin ở giai đoạn có kiểm soát, rồi validate trong môi trường bị hạn chế egress. Không dựa duy nhất vào việc các URL tình cờ phản hồi nhanh trong quá trình phát triển.

## 9. Thiết kế quy trình validate XML an toàn trong CI

Một pipeline phù hợp chia rõ hai chính sách:

- **Đầu vào tin cậy cần DTD:** dùng `<xmlcatalog>` ánh xạ DTD/version cục bộ; kiểm soát fallback của resolver và cấm truy cập mạng ngoài dự kiến.
- **Đầu vào không tin cậy:** tắt DOCTYPE/entity ngoài/XInclude và giới hạn tài nguyên; không cần DTD/catalog trừ khi có yêu cầu chức năng đã được xác định.

Sơ đồ:

```text
Checkout commit đã duyệt
          |
          v
Kiểm tra bộ file XML/DTD/schema + phiên bản công cụ
          |
          v
     Phân loại XML
      /           \
     /             \
Tin cậy,         Không đáng tin,
cần DTD          không cần DOCTYPE
   |                  |
   v                  v
Catalog cục bộ      Parser an toàn:
+ parser chính sách  reject DOCTYPE
   |                disable external entity
   |                disable XInclude
   |                  |
   +--------+---------+
            |
            v
    Thử với mạng bị chặn
            |
      +-----+-----+
      |           |
    PASS        FAIL
      |           |
      v           v
Build tiếp    Chẩn đoán tham chiếu,
              fail hoặc sửa input
```

### Ví dụ chuỗi target cho tài liệu có DTD

Trong dự án phần 4, có thể thêm một target bắt buộc:

```xml
<target name="verify-documentation" depends="validate-docs">
    <echo message="Tài liệu XML đã qua validation với DTD cục bộ."/>
</target>
```

Rồi để CI gọi:

```bash
ant -noinput -f build.xml verify-documentation
```

Cấu hình `-noinput` tránh task hỏi tương tác khi chạy trên CI. Tuy nhiên, việc target thành công **chỉ cho biết validation không báo lỗi**, chưa tự chứng minh không có truy cập mạng. Cần thử trong môi trường có giới hạn network và có tình huống định danh lạ để chắc rằng resolver không fallback không mong muốn.

### Ba phép thử nên có trong bộ kiểm chứng CI

**Trường hợp A — định danh được phép:** XML `manual.xml` khai báo đúng `PUBLIC ID`. File DTD cục bộ tồn tại, parser nhận catalog, validation thành công ngay cả khi không có mạng.

**Trường hợp B — định danh không được phép:** thay bằng một `PUBLIC ID`/`SYSTEM ID` không có trong catalog ở một fixture riêng. Với chính sách **fail closed**, việc validate phải dừng có kiểm soát; nó không được tự động tải một DTD chưa duyệt. Đừng dùng các URL trỏ tới dịch vụ nội bộ thật để thử.

**Trường hợp C — entity ngoài trên XML không đáng tin:** dùng một fixture có `DOCTYPE`/`ENTITY` và kiểm tra helper an toàn từ phần 5 từ chối. Với parser không hỗ trợ feature bắt buộc, job cũng phải thất bại thay vì silently pass.

Ghi rõ kết quả mong đợi trong CI: **A được phép; B và C bị từ chối**. Các kiểm thử này là những hành vi cần có khi tích hợp giải pháp, không phải thứ mà một cấu hình catalog tự động đảm bảo.

## 10. Chẩn đoán lỗi: phân biệt thiếu catalog và parser không an toàn

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| Build bị treo khi validate XML | Parser đang truy cập URL không phản hồi; có thể xử lý entity lớn | Kiểm tra log resolver, timeout và network; tìm `DOCTYPE`/schema import. |
| Cùng commit nhưng chỉ CI offline thất bại | DTD/schema chưa được lưu cục bộ hoặc catalog không được áp dụng | Kiểm tra ID trong XML, đường dẫn catalog, tập file ở runner. |
| Validation báo không tìm được DTD dù catalog đã khai báo | `PUBLIC ID` không khớp, task không nhận catalog hoặc file local sai path | Đối chiếu định danh chính xác; dùng `location` dựa trên `basedir`. |
| XML không đáng tin vẫn đọc entity ngoài | Parser hỗ trợ external entities hoặc helper chỉ kiểm tra một lượt parse khác | Cấu hình parser **thực sự tiêu thụ XML** và fail khi không hỗ trợ cờ. |
| Parser báo không nhận feature `disallow-doctype-decl` | Provider XML không hỗ trợ Xerces feature | Chọn parser có hỗ trợ hoặc cơ chế bảo vệ tương đương; không bỏ cờ rồi mặc định pass. |
| Mở DTD local được nhưng sau đó vẫn gọi URL khác | DTD có external parameter entity hoặc schema/XSLT tham chiếu tiếp | Xét toàn bộ cây dependency và chặn fallback. |
| Build fail sau khi đặt `accessExternalDTD=""` | Parser đang cần DTD ngoài hoặc resolver không hoạt động như kỳ vọng | Xác định luồng phân giải; chỉ cho phép resource cần thiết, tránh bật `all`. |
| File XML lạ làm job dùng nhiều CPU/RAM | Entity expansion, recursion hoặc tài liệu quá lớn | Từ chối DOCTYPE với đầu vào không tin, giới hạn bộ nhớ/thời gian và số lượng dữ liệu. |
| Không có cảnh báo network nhưng kết quả không tái lập | DTD/schema địa phương bị thay thế, toolchain thay hoặc resource dynamic | Pin/checksum toàn bộ input và so sánh sản phẩm. |
| Build script từ PR chạy lệnh tùy ý | Kẻ sửa `build.xml` đã có quyền điều khiển task Ant | Cô lập job PR; không cấp secret, quyền mạng nội bộ hoặc quyền deploy cho script chưa duyệt. |

### Đừng xử lý lỗi bằng cách nới quyền vô điều kiện

Các “bản sửa nhanh” kiểu bật lại mọi external entity, `accessExternalDTD=all`, tắt `failonerror` hoặc bỏ qua validation có thể làm job xanh nhưng vô hiệu hóa chính sách an toàn. Thay vào đó, xác định **tài nguyên nào thực sự cần**, lưu đúng phiên bản cục bộ, cấu hình resolver chính xác và giữ điều kiện fail khi phát hiện tham chiếu ngoài danh sách.

## 11. Chính sách kiểm soát thay đổi catalog và DTD

Catalog có thể che khuất một thay đổi nội dung DTD nếu tên file giữ nguyên. Một quy trình quản lý tốt nên ghi lại:

| Thành phần | Thông tin nên quản lý |
| --- | --- |
| `docs/manual.xml` | Định danh PUBLIC/SYSTEM được tham chiếu; phiên bản tài liệu |
| `schemas/manual.dtd` | Nguồn lấy, phiên bản, SHA-256 và người review |
| `build.xml` | Mục catalog ánh xạ, parser task và `failonerror` |
| Toolchain | JDK/Ant và plugin/parser XML có liên quan |
| CI policy | Có hay không network, giá trị JAXP EAP và quyền runner |
| Kết quả validation | Commit, target, phiên bản công cụ, tập tài liệu và kết quả PASS/FAIL |

Ví dụ bản kê khai dưới dạng text:

```text
Catalog rule:
  publicId  = -//EXAMPLE//DTD Manual 1.0//EN
  localFile = schemas/manual.dtd
  checksum  = <sha256-64-hex-da-duoc-duyet>

CI policy:
  trusted-xml-dtd-validation = offline, local catalog only
  untrusted-xml             = reject DOCTYPE and external resources
  failed-resolution         = fail build
```

Giá trị `<sha256-64-hex-da-duoc-duyet>` là placeholder, không phải checksum thật. Không tự tạo checksum “chuẩn” từ DTD vừa tải từ URL chưa đáng tin rồi coi là đã xác minh. Nên đối chiếu với bản đã được phê duyệt qua review/checksum/chữ ký theo quy định của dự án.

Khi nâng DTD hoặc schema:

1. Chọn đúng phiên bản và xác nhận nguồn cung cấp.
2. Đưa file được kiểm soát vào repository hoặc artifact source nội bộ được khóa nội dung.
3. Cập nhật catalog và checksum; tránh dùng URL `latest` làm nguồn thực thi.
4. Chạy validation trên dữ liệu dự kiến và các fixture không được phép.
5. Review cả tác động đến cách parse và sản phẩm build; ghi lại thay đổi.

## 12. Bài thực hành: thiết lập catalog và thử chính sách từ chối

### Bài A — Validate DTD cục bộ

Tạo ba file `schemas/manual.dtd`, `docs/manual.xml` và `build.xml` ở phần 4. Chạy target `validate-docs`. Sau đó thực hiện lại trong môi trường tắt mạng hoặc chặn egress tới nguồn DTD minh họa. Mục tiêu là chứng minh **không cần tải DTD từ bên ngoài** trong cấu hình đã cho phép.

### Bài B — Kiểm tra file không hợp lệ

Giữ nguyên DTD nhưng sửa XML thành:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE manual PUBLIC
    "-//EXAMPLE//DTD Manual 1.0//EN"
    "https://schemas.example.invalid/manual.dtd">
<manual>
    <paragraph>Thiếu title nên không phù hợp DTD.</paragraph>
</manual>
```

Quan sát target `xmlvalidate` thất bại vì cấu trúc không đáp ứng yêu cầu `(title, paragraph+)`. Phép thử này kiểm tra **validation hoạt động**, không chỉ kiểm tra file XML đọc được.

### Bài C — Tham chiếu không có trong catalog

Tạo một fixture riêng thay `PUBLIC ID` thành `-//EXAMPLE//DTD Unknown 9.9//EN`. Chạy trong môi trường không cho phép egress. Ghi nhận lỗi phân giải; đảm bảo pipeline không thành công bằng cách tải một URL lạ hoặc bỏ qua kiểm tra.

### Bài D — XML bên ngoài có DOCTYPE

Tạo file `docs/untrusted.xml` với khai báo DOCTYPE đơn giản:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE note [
    <!ELEMENT note (#PCDATA)>
]>
<note>Đầu vào chưa đáng tin</note>
```

Chạy `ant check-untrusted-xml -Dxml.input=docs/untrusted.xml` theo helper ở phần 5. Mặc dù DTD nội tuyến vô hại, policy của helper là **cấm toàn bộ DOCTYPE**, vì thế job phải dừng. Điều này giúp tránh chính sách chỉ chặn URL nhất định nhưng vẫn để lại khả năng khai báo entity ngoài.

### Bài E — Hai policy trong cùng repository

Đặt `manual.xml` trong nhóm **trusted documentation** có catalog và `untrusted.xml` trong nhóm **external input** không dùng DTD. Tách target và quyền thực thi tương ứng. Đừng cho phép một file bên ngoài chọn target validation “tin cậy” để né chính sách từ chối DOCTYPE.

## 13. Câu hỏi tự kiểm tra

1. Khác biệt giữa tham chiếu DTD bằng `PUBLIC ID` và việc parser thực sự đi tải `SYSTEM URL` là gì?
2. Catalog có một mục ánh xạ hợp lệ thì vì sao một entity hoặc schema lạ vẫn có thể dẫn tới truy cập ngoài?
3. Khi XML từ người dùng không cần DTD, nên bật catalog hay cấu hình parser từ chối DOCTYPE?
4. Nếu `xmlvalidate` có `failonerror="true"`, điều đó có tự chứng minh build không truy cập Internet không?
5. Tại sao `javax.xml.accessExternalDTD` không giải quyết được toàn bộ `xsl:include`, `document()` hoặc một lệnh HTTP do task tự thực hiện?
6. Khi helper Java không hỗ trợ một SAX feature bảo mật quan trọng, nên tiếp tục parse hay fail build?
7. Vì sao không thể coi một file `build.xml` do người ngoài kiểm soát là an toàn chỉ nhờ có XML Catalog?
8. Những thông tin nào cần pin để cùng một commit không bất ngờ dùng DTD/schema khác nhau trên hai runner?

## 14. Tổng kết

Trong Ant, kiểm soát XML bên ngoài là việc **quy định rõ parser được đọc tài nguyên nào** và thực thi quy định ở cả task, JVM lẫn runner CI. Với XML không đáng tin, ưu tiên từ chối DOCTYPE/entity ngoài và giới hạn tài nguyên. Với tài liệu thật sự cần DTD, dùng `<xmlcatalog>` để ánh xạ định danh đã biết sang bản cục bộ, quản lý phiên bản/checksum và **không cho phép fallback ngoài danh sách**. Mọi cấu hình đều cần được thử trong môi trường hạn chế mạng, vì một catalog được khai báo hoặc một lượt validation PASS chưa tự chứng minh rằng mọi truy cập ngoài đã bị kiểm soát.

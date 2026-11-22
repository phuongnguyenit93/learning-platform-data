# Kiểm soát phân tích XML, thực thể ngoài và truy cập tài nguyên

## 1. XPath cần một cây XML đã được tạo an toàn

Khi dùng XPath trên DOM, chuỗi xử lý có hai phần:

```text
Nguồn XML → trình phân tích XML → cây DOM → biểu thức XPath → kết quả
                   ↑
       Đọc DTD, thực thể, XInclude hoặc tài nguyên phụ
       có thể xảy ra tại đây nếu được cho phép.
```

Một biểu thức đơn giản như `string(/catalog/title)` không nói gì về cách cây DOM được tạo. Nếu trình phân tích đã đọc một tệp hoặc truy cập mạng theo chỉ dẫn trong XML, việc XPath chỉ chọn một phần tử sau đó không đảo ngược được hành động ấy.

Vì vậy, khi nhận XML từ bên ngoài, cần xác định rõ:

- Ai cung cấp tài liệu chính và giới hạn kích thước của nó?
- Ứng dụng có thực sự cần DTD, thực thể tùy chỉnh, XInclude hoặc schema ngoài không?
- Thành phần nào được phép mở tệp, kết nối mạng hoặc phân giải tài nguyên?
- Giới hạn nào ngăn XML quá sâu, quá nhiều thuộc tính hoặc chiếm quá nhiều tài nguyên?

Bài tập trung vào trường hợp phổ biến: **ứng dụng chỉ cần đọc XML rồi truy vấn XPath, không cần DTD hoặc tài nguyên ngoài**. Mã hoàn chỉnh dùng Java 17+ với bộ phân tích DOM có sẵn trong JDK.

## 2. Các cơ chế cần phân biệt

### DTD và thực thể ngoài

DTD có thể khai báo một thực thể có nội dung nằm trong tài nguyên khác. Ví dụ minh họa:

```xml
<!DOCTYPE catalog [
  <!ENTITY external SYSTEM "file:///blocked-demo-never-open.txt">
]>
<catalog>
  <title>&external;</title>
</catalog>
```

Nếu cấu hình cho phép, trình phân tích có thể mở tài nguyên được chỉ định và đưa nội dung vào cây XML. Với tài liệu không tin cậy, cơ chế này có thể gây đọc tệp ngoài ý muốn hoặc yêu cầu mạng từ máy chủ. Đây là nhóm rủi ro thường được gọi là XML External Entity (XXE).

DTD nội bộ cũng có thể tạo sự mở rộng thực thể lớn mà không cần mạng. Vì vậy, “chặn HTTP” không đồng nghĩa đã kiểm soát DTD.

### XInclude

Phần tử `xi:include` là một cơ chế khác để ghép tài nguyên vào tài liệu. Tắt xử lý DTD không tự diễn đạt chính sách XInclude. Khi không có nhu cầu ghép tài liệu, đặt `setXIncludeAware(false)`.

### Schema và biến đổi XML

Nếu ứng dụng thêm bước xác thực XSD hoặc biến đổi XSLT, các bước ấy có thể có tài nguyên phụ riêng. Cấu hình parser DOM không tự cấu hình mọi `SchemaFactory`, `Validator` hoặc `TransformerFactory` khác trong hệ thống.

Thiết kế chính sách theo từng bộ xử lý thực sự được dùng, không tìm một cờ chung rồi giả định toàn bộ chuỗi đã được khóa.

## 3. Chính sách cho đầu vào không cần DTD

| Kiểm soát | Vai trò |
|---|---|
| Từ chối `DOCTYPE` | Không chấp nhận tài liệu dựa vào DTD, kể cả DTD nội bộ |
| `ACCESS_EXTERNAL_DTD = ""` | Không cho các giao thức truy cập DTD và tham chiếu thực thể ngoài |
| `ACCESS_EXTERNAL_SCHEMA = ""` | Không cho truy cập schema ngoài trong phạm vi bộ xử lý tương ứng |
| `setXIncludeAware(false)` | Không thực hiện ghép tài liệu qua XInclude |
| `FEATURE_SECURE_PROCESSING = true` | Bật chế độ xử lý có giới hạn an toàn của bộ thực thi |
| Giới hạn kích thước, độ sâu, số thuộc tính | Kiểm soát tài nguyên dù XML không chứa DTD |
| Resolver từ chối | Không tự mở tài nguyên khi có yêu cầu phân giải ngoài |
| Dừng khi không cấu hình được | Không tiếp tục với cấu hình bảo vệ bị thiếu |

Các thuộc tính truy cập ngoài nhận danh sách giao thức. Chuỗi rỗng nghĩa là không cho phép giao thức nào; `"file"` vẫn cho đọc tệp và `"all"` cho phép mọi giao thức. Không dùng `"file"` nếu chính sách của ứng dụng là không đọc tài nguyên ngoài. [Ý nghĩa các thuộc tính truy cập ngoài](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/XMLConstants.html).

Không coi một mặc định của JDK đang chạy là hợp đồng vĩnh viễn. Cấu hình rõ trên factory của thành phần xử lý giúp chính sách nằm gần mã sử dụng nó.

## 4. Ví dụ hoàn chỉnh: phân tích trước, đánh giá XPath sau

Lưu thành `SafeXPathXmlDemo.java`. Không cần dependency ngoài JDK.

```java
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.xpath.XPath;
import javax.xml.xpath.XPathFactory;
import org.w3c.dom.Document;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;
import org.xml.sax.helpers.DefaultHandler;

public class SafeXPathXmlDemo {
    private static final int MAX_BYTES = 64 * 1024;
    private static final AtomicInteger RESOLVER_CALLS = new AtomicInteger();

    static Document parseXml(byte[] bytes) throws Exception {
        if (bytes.length > MAX_BYTES) {
            throw new IllegalArgumentException("XML exceeds input limit");
        }

        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newDefaultInstance();
        factory.setNamespaceAware(true);
        factory.setValidating(false);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);
        factory.setAttribute("jdk.xml.maxElementDepth", "64");
        factory.setAttribute("jdk.xml.elementAttributeLimit", "64");

        DocumentBuilder builder = factory.newDocumentBuilder();
        builder.setEntityResolver((publicId, systemId) -> {
            RESOLVER_CALLS.incrementAndGet();
            throw new SAXException("External entity resolution denied");
        });
        builder.setErrorHandler(new DefaultHandler() {
            @Override
            public void error(SAXParseException failure) throws SAXException {
                throw failure;
            }

            @Override
            public void fatalError(SAXParseException failure) throws SAXException {
                throw failure;
            }
        });

        try (ByteArrayInputStream input = new ByteArrayInputStream(bytes)) {
            return builder.parse(input);
        }
    }

    static Document parseXml(String xml) throws Exception {
        return parseXml(xml.getBytes(StandardCharsets.UTF_8));
    }

    static void expectRejected(String label, String xml) throws Exception {
        try {
            parseXml(xml);
        } catch (SAXException expected) {
            System.out.println(label + ": REJECTED");
            return;
        }
        throw new AssertionError(label + ": unexpectedly accepted");
    }

    public static void main(String[] args) throws Exception {
        XPathFactory xpathFactory = XPathFactory.newDefaultInstance();
        xpathFactory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        XPath xpath = xpathFactory.newXPath();

        Document normal = parseXml(
                "<catalog><title>Safe &amp; local</title></catalog>");
        System.out.println("normal: "
                + xpath.evaluate("string(/catalog/title)", normal));

        String externalEntity = """
                <!DOCTYPE catalog [
                  <!ENTITY external SYSTEM "file:///blocked-demo-never-open.txt">
                ]>
                <catalog><title>&external;</title></catalog>
                """;
        expectRejected("external-entity", externalEntity);

        String internalEntity = """
                <!DOCTYPE catalog [<!ENTITY greeting "hello">]>
                <catalog><title>&greeting;</title></catalog>
                """;
        expectRejected("internal-doctype", internalEntity);

        expectRejected("depth-limit", "<n>".repeat(65) + "</n>".repeat(65));

        StringBuilder attributes = new StringBuilder("<n");
        for (int i = 0; i < 65; i++) {
            attributes.append(" a").append(i).append("='x'");
        }
        attributes.append("/>");
        expectRejected("attribute-limit", attributes.toString());

        try {
            parseXml(new byte[MAX_BYTES + 1]);
            throw new AssertionError("Oversized input accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("byte-limit: REJECTED");
        }

        Document xinclude = parseXml("""
                <catalog xmlns:xi="http://www.w3.org/2001/XInclude">
                  <xi:include href="file:///blocked-demo-never-open.txt"
                              parse="text"/>
                </catalog>
                """);
        String includeCount = xpath.evaluate(
                "count(/catalog/*[local-name()='include'"
                + " and namespace-uri()='http://www.w3.org/2001/XInclude'])",
                xinclude);
        System.out.println("xinclude-elements-kept: " + includeCount);

        if (RESOLVER_CALLS.get() != 0) {
            throw new AssertionError("Unexpected resolver invocation");
        }
        System.out.println("resolver-calls: " + RESOLVER_CALLS.get());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 SafeXPathXmlDemo.java
java SafeXPathXmlDemo
```

Stdout:

```text
normal: Safe & local
external-entity: REJECTED
internal-doctype: REJECTED
depth-limit: REJECTED
attribute-limit: REJECTED
byte-limit: REJECTED
xinclude-elements-kept: 1
resolver-calls: 0
```

URI `file:///blocked-demo-never-open.txt` chỉ là đích thử nghiệm không được mở. Không thay nó bằng đường dẫn dữ liệu thật để làm bài. Tài liệu có khai báo thực thể bị từ chối tại `DOCTYPE`; trường hợp XInclude được giữ nguyên như phần tử thông thường vì xử lý XInclude đang tắt.

### 4.1. Chọn rõ bộ phân tích của JDK

`DocumentBuilderFactory.newDefaultInstance()` chọn bộ thực thi mặc định có sẵn trong JDK. Ví dụ chủ động dùng nó vì có hai thuộc tính giới hạn `jdk.xml.*` và một tính năng từ chối DOCTYPE được bộ phân tích ấy hỗ trợ.

Nếu ứng dụng cần một bộ thực thi bên thứ ba qua cơ chế tìm provider, phải xác minh bộ đó hiểu và thực thi các thiết lập bắt buộc. Không bắt lỗi “không hỗ trợ thuộc tính” rồi bỏ qua và tiếp tục. `newDocumentBuilder()` chỉ được gọi sau khi cấu hình hoàn tất. [API DocumentBuilderFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/parsers/DocumentBuilderFactory.html).

Tên tính năng `http://apache.org/xml/features/disallow-doctype-decl` là định danh cấu hình, không phải URL mà chương trình tải về.

### 4.2. Từ chối DTD khác với không xác thực DTD

`setValidating(false)` không tự cấm mọi xử lý DTD hoặc thực thể. Trong ví dụ, thiết lập quan trọng để từ chối DTD là `disallow-doctype-decl = true`.

Cả tài liệu khai báo thực thể ngoài lẫn tài liệu chỉ khai báo `greeting` nội bộ đều bị từ chối. Đây là chính sách có chủ đích: nếu hợp đồng đầu vào không cần DTD, không cho DTD đi vào chuỗi xử lý.

Các tham chiếu chuẩn như `&amp;` vẫn hoạt động trong XML bình thường. Dòng `normal: Safe & local` minh họa điều đó.

JDK hiện hành còn có thuộc tính `jdk.xml.dtd.support` với giá trị `deny` để từ chối DTD. Thuộc tính này có từ JDK 22, nên mã chạy với mốc Java 17 ở đây không dựa vào nó. Khi triển khai trên JDK 22+, có thể lựa chọn chính sách đó theo tài liệu của bản JDK; không đặt chồng nhiều cơ chế rồi bỏ qua quy tắc ưu tiên giữa chúng. [Thuộc tính và mốc phiên bản của java.xml](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/module-summary.html).

### 4.3. Không dùng một cờ thay cho toàn bộ chính sách

`setExpandEntityReferences(false)` xuất hiện như cấu hình bổ sung; riêng nó không có nghĩa đã chặn mọi truy cập tài nguyên ngoài hoặc mọi cách xử lý DTD.

Tương tự, chỉ bật `FEATURE_SECURE_PROCESSING` không thay thế việc quyết định rõ có cho DTD, XInclude hoặc tài nguyên ngoài hay không. Các mặc định và giới hạn có thể khác theo bộ thực thi, phiên bản và nguồn cấu hình. Ví dụ đặt trực tiếp các chính sách cần thiết thay vì suy ra chúng từ một cờ.

### 4.4. Resolver từ chối khác với resolver trả null

Bộ `EntityResolver` trong ví dụ ném `SAXException` nếu được yêu cầu phân giải tài nguyên ngoài. Trả `null` không có nghĩa là “cấm”; nó cho trình phân tích tiếp tục cách phân giải mặc định.

Resolver này không bảo vệ việc mở tài liệu chính từ một URL. Giao diện phân giải thực thể chỉ can thiệp vào các thực thể ngoài thuộc phạm vi của nó, không phải mọi truy cập tài nguyên của ứng dụng. [Hợp đồng EntityResolver](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/org/xml/sax/EntityResolver.html).

Kết quả `resolver-calls: 0` cho thấy trong các ca thử, yêu cầu xử lý tài nguyên ngoài không đi đến resolver. Ca DOCTYPE bị từ chối sớm; ca XInclude không được thực thi. Đây là minh chứng cho đúng bộ ca thử và cấu hình ấy, không phải phép chứng minh cho mọi parser có thể được thay vào sau này.

## 5. Giới hạn tài nguyên phải nằm trước và trong phân tích

Ví dụ chọn các con số để bài thực hành dễ quan sát:

- Đầu vào tối đa 64 KiB.
- Độ sâu phần tử tối đa 64.
- Tối đa 64 thuộc tính trên một phần tử.

Chúng không phải mức phù hợp cho mọi ứng dụng. Hãy dựa trên tài liệu hợp lệ thực tế, dung lượng bộ nhớ và tải đồng thời để chọn giới hạn, rồi kiểm thử ở ranh giới.

Giới hạn byte trong `parseXml(byte[])` ngăn dữ liệu quá lớn đi vào parser, nhưng mảng byte đã được tạo trước đó. Khi nhận dữ liệu qua HTTP hoặc một `InputStream`, cần giới hạn ngay trong quá trình đọc; không gọi `readAllBytes()` trên luồng không giới hạn rồi mới kiểm tra. Nếu đầu vào được giải nén, giới hạn cả kích thước sau giải nén.

Độ sâu và số thuộc tính không thay thế giới hạn tổng kích thước. Ngược lại, tài liệu nhỏ vẫn có thể rất sâu. Chúng giải quyết các dạng tiêu thụ tài nguyên khác nhau.

Hai thuộc tính `jdk.xml.maxElementDepth` và `jdk.xml.elementAttributeLimit` áp dụng cho bộ phân tích của JDK; tên `jdk.xml.*` được dùng trong ví dụ. Không sao chép giá trị mặc định từ một bản JDK khác rồi coi đó là giới hạn đã được ứng dụng thiết lập.

Giới hạn parser cũng không phải thời hạn tuyệt đối cho một biểu thức XPath tùy ý. Trong ví dụ, biểu thức do ứng dụng kiểm soát. Nếu sản phẩm cho phép người dùng viết biểu thức, cần giới hạn riêng độ phức tạp truy vấn, dữ liệu và tải xử lý; không coi việc XML không có DTD là đủ.

## 6. Quản lý tài nguyên ngoài nếu nghiệp vụ thật sự cần

Có ứng dụng hợp lệ cần XSD, DTD hoặc dữ liệu phụ do tổ chức quản lý. Khi đó không đổi toàn bộ thành `"all"` chỉ để một tài liệu chạy được.

Một phương án cần được thiết kế riêng:

1. Xác định tập tài nguyên phụ được phép, có danh tính và phiên bản ổn định.
2. Đóng gói hoặc cung cấp tài nguyên đã kiểm soát qua resolver/catalog.
3. Chỉ phân giải các định danh được cho phép; từ chối trường hợp còn lại.
4. Giữ giới hạn kích thước, độ sâu và thời gian/tải ở các tầng phù hợp.
5. Kiểm thử cả trường hợp thiếu tài nguyên, định danh lạ và tài nguyên phụ tiếp tục tham chiếu tài nguyên khác.

Nếu resolver tự mở URL hoặc trả về một luồng đã được mở, chính resolver đang thực hiện truy cập ấy. Thuộc tính cấm giao thức của parser không thay thế kiểm soát bên trong resolver. Không viết resolver “thử mở URL đầu vào, thất bại thì trả null”.

Đây là một hợp đồng đầu vào khác với ví dụ “không có DTD” của bài; cần đánh giá toàn bộ chuỗi xử lý, không chỉ bỏ một dòng cấu hình. [Hướng dẫn JAXP về truy cập ngoài, resolver và catalog](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html).

## 7. Những giới hạn hay bị hiểu sai

### Chặn tài nguyên phụ không chặn URL đầu vào chính

Nếu ứng dụng nhận URL từ người dùng rồi tự mở kết nối, yêu cầu mạng đã phát sinh trước khi parser tạo DOM. Tương tự, truyền một đường dẫn hoặc URI cho overload `parse(...)` không phải là cách tự động tạo giới hạn truy cập cho nguồn chính.

Ví dụ dùng `ByteArrayInputStream` từ dữ liệu đã nhận, không cho parser chọn nơi tải tài liệu chính. Nếu sản phẩm phải tải tài liệu từ xa, lớp tải dữ liệu cần kiểm soát đích, chuyển hướng, thời hạn và dung lượng theo chính sách của sản phẩm.

### Tắt XInclude không nhất thiết loại bỏ phần tử xi:include

Dòng `xinclude-elements-kept: 1` là kết quả có chủ đích. Parser không tải nội dung để thay thế phần tử, nhưng phần tử ấy vẫn có thể tồn tại trong DOM.

Nếu hợp đồng tài liệu cấm xuất hiện phần tử XInclude, hãy kiểm tra và từ chối nó như một điều kiện riêng. Không chuyển DOM sang một thành phần khác có bật XInclude rồi giả định chính sách trước đó tiếp tục được giữ.

### Biến XPath không giải quyết XXE

Biến XPath giúp tách giá trị khỏi cấu trúc biểu thức. XXE thuộc quá trình tạo cây XML. Hai cơ chế xử lý hai vấn đề khác nhau; một truy vấn được tham số hóa vẫn có thể chạy trên DOM đã được tạo bằng cấu hình không phù hợp.

### Cấu hình SchemaFactory hoặc TransformerFactory là trách nhiệm riêng

Khi bổ sung xác thực hoặc biến đổi, cấu hình quyền truy cập ngoài trên chính các factory/processor tương ứng. Không đặt `ACCESS_EXTERNAL_STYLESHEET` lên `DocumentBuilderFactory` chỉ vì cùng là hằng XML: thuộc tính dành cho bộ xử lý khác không tự trở thành cấu hình DOM hợp lệ.

### Chặn ngoài chưa bảo đảm truy vấn luôn nhanh

DOM chiếm bộ nhớ, XPath có thể duyệt nhiều nút, và nhiều yêu cầu đồng thời có thể vượt ngân sách tài nguyên dù từng tài liệu đều hợp lệ. Cần kiểm thử với dữ liệu và tải thực tế. Một lỗi giới hạn phải trở thành kết quả từ chối rõ ràng, không tự động tăng ngưỡng hoặc thử lại bằng parser ít hạn chế hơn.

## 8. Kiểm thử và áp dụng vào ứng dụng

Bộ ví dụ đã kiểm tra tài liệu thường, DOCTYPE nội bộ/ngoài, độ sâu, thuộc tính, kích thước và hành vi XInclude. Khi đưa vào ứng dụng, bổ sung các trường hợp phù hợp hợp đồng dữ liệu:

- Tài liệu hợp lệ sát giới hạn và vượt giới hạn một đơn vị.
- Các tham chiếu ngoài qua giao thức hoặc vị trí không được phép.
- Nội dung sai cú pháp, lỗi mã hóa và nguồn bị ngắt giữa chừng.
- Tài liệu có namespace và nội dung mà XPath dự kiến phải tìm thấy.
- Cấu hình bắt buộc bị provider từ chối: ứng dụng phải dừng khởi tạo thành phần xử lý.
- Thay đổi phiên bản JDK/provider: chạy lại các ca từ chối và kiểm tra không có truy cập ngoài trong môi trường thử nghiệm cô lập.

Tạo builder sau khi cấu hình hoàn tất; không tiếp tục sử dụng DOM từ một lần phân tích thất bại. Ví dụ tạo builder mới cho mỗi lần gọi để vòng đời rõ ràng, không dùng chung một builder đang hoạt động cho nhiều yêu cầu.

Khi ghi lỗi, giữ thông tin giai đoạn và nguyên nhân cần chẩn đoán. Không tự ghi toàn bộ XML hoặc nội dung tài nguyên vào log. Mục đích là biết vì sao đầu vào bị từ chối, trong khi vẫn thực thi đúng chính sách đã chọn.

## 9. Thực hành

1. Đổi XML thường thành nội dung có `&lt;` và `&amp;`. Xác nhận các tham chiếu chuẩn vẫn được đọc đúng mà không cần DTD.
2. Đổi độ sâu từ 65 xuống 64 rồi chạy lại riêng trường hợp độ sâu. Quan sát ranh giới của cấu hình đang dùng.
3. Đổi số thuộc tính từ 65 xuống 64. Xác nhận tài liệu ở ngưỡng được chấp nhận.
4. Với DOM chứa `xi:include`, viết một kiểm tra từ chối nếu hợp đồng đầu vào không cho phép phần tử thuộc namespace XInclude.
5. Tách hàm đọc luồng có giới hạn khỏi hàm tạo DOM, bảo đảm không tạo mảng byte không giới hạn trước khi gọi `parseXml`.
6. Mô tả nguồn XML chính, tài nguyên phụ được phép và nơi kiểm soát từng loại trong một ứng dụng cụ thể trước khi thêm bất kỳ resolver tải tài nguyên nào.

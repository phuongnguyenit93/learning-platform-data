# Giới hạn tài nguyên khi xử lý XML không tin cậy

## 1. XML hợp lệ vẫn có thể tốn tài nguyên quá mức

Một tài liệu XML có thể đúng cú pháp nhưng quá lớn, quá sâu hoặc chứa quá nhiều nội dung để dịch vụ xử lý trong ngân sách của một yêu cầu. Một biểu thức XPath cũng có thể ngắn nhưng phải duyệt nhiều nút, tạo nhiều kết quả hoặc được đánh giá lặp lại quá nhiều lần.

Vì vậy cần phân biệt hai nhóm:

- **Quyền truy cập:** parser/bộ xử lý có được tải DTD, entity hoặc nguồn ngoài không?
- **Ngân sách tài nguyên:** được đọc bao nhiêu byte, xây cây sâu/rộng đến đâu, thực hiện truy vấn nào, trả bao nhiêu dữ liệu và xử lý bao nhiêu yêu cầu cùng lúc?

Chặn nguồn ngoài là cần thiết trong một chính sách không dùng chúng, nhưng không đủ để ngăn một tài liệu nội tuyến rất lớn làm cạn bộ nhớ hoặc CPU. Ngược lại, giới hạn kích thước đầu vào không tự cấm việc parser truy cập một tài nguyên ngoài mà XML tham chiếu. [Hướng dẫn JAXP Security hiện hành](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html)

Bài dùng cơ chế JAXP hiện hành. Chương trình minh họa yêu cầu **JDK 21 trở lên**, dùng parser và bộ XPath mặc định của JDK; `XPathFactory.setProperty` có từ Java 18. Các con số là ngưỡng nhỏ để thực nghiệm, không phải cấu hình chuẩn cho mọi ứng dụng.

## 2. Đặt giới hạn trên toàn đường xử lý

```text
Nhận nguồn XML
    → giới hạn byte/thời gian đọc
    → nếu giải nén: giới hạn cả dữ liệu sau giải nén
    → parse với chính sách nguồn ngoài và cấu trúc
    → kiểm tra mô hình dữ liệu ứng dụng
    → đánh giá XPath được kiểm soát
    → giới hạn kết quả và đầu ra
    → giải phóng tài nguyên theo vòng đời
```

Mỗi lớp giải quyết một kiểu tiêu thụ khác nhau:

| Lớp giới hạn | Ngăn điều gì? | Không thay thế cho |
| --- | --- | --- |
| Byte đầu vào | Đọc/giữ toàn bộ một nguồn quá lớn | Độ sâu, số nút và độ phức tạp truy vấn |
| Đọc/kết nối có thời hạn | Chờ dữ liệu đến vô hạn ở tầng nguồn | Thời gian CPU của evaluate |
| Cấu trúc parser | Cây quá sâu, quá nhiều thuộc tính, tên quá dài, mở rộng entity vượt ngưỡng | Giới hạn tổng heap của cả JVM |
| Biểu thức XPath | Biểu thức chứa cấu trúc/toán tử vượt chính sách | Giới hạn thời gian thực thi tuyệt đối |
| Kết quả | Trả/giữ quá nhiều dữ liệu sau truy vấn | Tài nguyên đã tiêu trước khi kiểm tra kết quả |
| Mức đồng thời/hàng chờ | Quá nhiều tài liệu được xử lý/giữ cùng lúc | Giới hạn từng tài liệu |

Thời điểm kiểm tra quan trọng không kém con số. Parse xong một DOM khổng lồ rồi mới hỏi số nút là quá muộn để bảo vệ phần bộ nhớ đã cấp cho DOM ấy.

## 3. Giới hạn byte trước khi parse

Nếu ứng dụng đọc mạng/tệp, đặt ngưỡng ngay trên luồng dữ liệu. Không chỉ tin `Content-Length`, tên tệp hoặc `InputStream.available()`. `available()` không phải tổng kích thước còn lại; dữ liệu có thể đến theo từng đợt.

Một mẫu đơn giản cho tài liệu nhỏ là đọc tối đa `N + 1` byte. Nếu có byte thứ `N + 1`, từ chối toàn bộ; nếu nguồn kết thúc trong N byte, mới chuyển dữ liệu đã giới hạn cho parser. `readNBytes` giúp giới hạn lượng đọc được yêu cầu, nhưng có thể chờ dữ liệu/EOF; thời hạn đọc phải được tầng nguồn xử lý. [InputStream.readNBytes](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/InputStream.html#readNBytes(int))

Không cắt đúng N byte rồi parse phần đầu và coi đó là tài liệu được chấp nhận. Đầu vào bị cắt có thể không còn XML hợp lệ hoặc thay nghĩa yêu cầu. Khi vượt ngưỡng, trả kết quả từ chối rõ ràng.

Nếu dữ liệu được nén, kích thước tệp nén nhỏ không chứng minh XML sau giải nén nhỏ. Đặt giới hạn dữ liệu sau giải nén ở trước parser, cùng ngân sách cho tầng nhận/nén phù hợp. Nếu đã tạo một `String` khổng lồ rồi mới kiểm tra độ dài, chi phí tạo chuỗi đã xảy ra; giới hạn tại nguồn giúp tránh bước đó.

Ngưỡng byte cũng khác số ký tự: UTF-8, UTF-16 và nội dung khai báo encoding không dùng cùng số byte cho mọi ký tự. Cần nói rõ đang giới hạn byte trên nguồn nào, hay ký tự sau giải mã, để không tạo khoảng trống giữa các tầng.

## 4. Cấu hình parser theo chính sách thực tế

`XMLConstants.FEATURE_SECURE_PROCESSING` (FSP) bật nền tảng hạn chế xử lý theo JAXP. Vẫn cần xác định các tài nguyên ngoài được phép và những ngưỡng ứng dụng cần; không coi một lệnh bật FSP là ngân sách tổng cho mọi tình huống.

Với một API chỉ nhận XML nội tuyến, không cần DTD và không cần nguồn ngoài, có thể đặt chính sách:

- Từ chối DOCTYPE.
- Không cho truy cập DTD/schema bên ngoài.
- Không bật XInclude.
- Cấu hình độ sâu, thuộc tính, tên và các giới hạn mở rộng nội dung liên quan.

Nếu ứng dụng thật sự cần DTD/schema/catalog, phải thiết kế một chính sách khác với nguồn được kiểm soát, giữ giới hạn tài nguyên và kiểm tra resolver. Không mở toàn bộ quyền mạng/tệp chỉ để một mẫu dữ liệu được parse thành công.

Một resolver tùy biến có thể cung cấp nguồn theo cách riêng; chính sách nguồn ngoài không thay thế việc kiểm tra chính resolver đó. Trong ví dụ, resolver từ chối mọi yêu cầu phân giải ngoài thay vì tự mở URL. [Nguồn ngoài, resolver và giới hạn JAXP](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html)

## 5. Các nhóm thuộc tính giới hạn của JDK

Các thuộc tính `jdk.xml.*` dưới đây là cấu hình của triển khai JDK; cần kiểm tra hỗ trợ trên JDK/provider thật sự triển khai. Đặt chúng trước khi tạo processor và xử lý lỗi cấu hình; không nuốt lỗi “không hỗ trợ thuộc tính” rồi vẫn nhận nguồn không tin cậy dưới giả định giới hạn đã có hiệu lực.

| Thuộc tính | Loại chi phí được giới hạn |
| --- | --- |
| `jdk.xml.maxElementDepth` | Độ sâu phần tử |
| `jdk.xml.elementAttributeLimit` | Số thuộc tính trên một phần tử |
| `jdk.xml.maxXMLNameLimit` | Kích thước tên XML và các thành phần tên/namespace liên quan |
| `jdk.xml.entityExpansionLimit` | Số lần mở rộng entity |
| `jdk.xml.totalEntitySizeLimit` | Tổng kích thước các entity theo cách đếm của parser |
| `jdk.xml.maxGeneralEntitySizeLimit` | Kích thước một general entity |
| `jdk.xml.entityReplacementLimit` | Tổng số nút trong các tham chiếu entity theo cách đếm của JDK |
| `jdk.xml.xpathExprGrpLimit` | Số nhóm trong một biểu thức XPath |
| `jdk.xml.xpathExprOpLimit` | Số toán tử trong một biểu thức XPath |

Một ngưỡng entity không phải giới hạn mọi văn bản của tài liệu. Chặn độ sâu cũng không chặn được một cây rất rộng nhưng nông. Cần kết hợp ngưỡng cấu trúc với byte đầu vào và quy tắc nghiệp vụ.

Với các processing-limit property này, giá trị không dương có nghĩa không giới hạn theo tài liệu JDK; đừng dùng `0` để biểu thị “không được phép có bất kỳ thứ gì”. Để không cho DOCTYPE, dùng cơ chế từ chối DOCTYPE, không mô phỏng bằng cách đặt ngưỡng mở rộng entity bằng 0. [Bảng processing limits của JDK](https://docs.oracle.com/en/java/javase/25/security/java-api-xml-processing-jaxp-security-guide.html)

Đừng nhầm `jdk.xml.xpathTotalOpLimit` với tổng số lần thực thi XPath hoặc ngân sách CPU mỗi yêu cầu. Thuộc tính này giới hạn tổng toán tử XPath trong một stylesheet XSLT, có phạm vi hỗ trợ khác với các ngưỡng biểu thức của `XPathFactory`.

## 6. Chương trình hoàn chỉnh: kiểm tra từ chối với đầu vào nhỏ

Lưu thành `BoundedXmlXPathDemo.java`. Ví dụ chọn ngưỡng 4096 byte, độ sâu 8, tối đa 8 thuộc tính trên một phần tử và tối đa 32 item. Nó dùng truy vấn cố định để đếm item; phần thử biểu thức phức tạp chỉ nhằm xác nhận ngưỡng toán tử.

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.xpath.XPathConstants;
import javax.xml.xpath.XPathExpression;
import javax.xml.xpath.XPathExpressionException;
import javax.xml.xpath.XPathFactory;
import org.w3c.dom.Document;
import org.xml.sax.SAXException;
import org.xml.sax.SAXParseException;
import org.xml.sax.helpers.DefaultHandler;

public class BoundedXmlXPathDemo {
    private static final int MAX_BYTES = 4096;
    private static final int MAX_MATCHES = 32;

    private static Document parseBounded(InputStream source) throws Exception {
        byte[] bytes = source.readNBytes(MAX_BYTES + 1);
        if (bytes.length > MAX_BYTES) {
            throw new IOException("XML byte limit exceeded");
        }

        DocumentBuilderFactory factory =
                DocumentBuilderFactory.newDefaultNSInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature(
                "http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setXIncludeAware(false);
        factory.setAttribute("jdk.xml.maxElementDepth", "8");
        factory.setAttribute("jdk.xml.elementAttributeLimit", "8");
        factory.setAttribute("jdk.xml.maxXMLNameLimit", "64");
        factory.setAttribute("jdk.xml.entityExpansionLimit", "64");
        factory.setAttribute("jdk.xml.totalEntitySizeLimit", "4096");
        factory.setAttribute("jdk.xml.maxGeneralEntitySizeLimit", "1024");
        factory.setAttribute("jdk.xml.entityReplacementLimit", "512");

        DocumentBuilder builder = factory.newDocumentBuilder();
        builder.setEntityResolver((publicId, systemId) -> {
            throw new SAXException("External resolution is disabled");
        });
        builder.setErrorHandler(new DefaultHandler() {
            @Override
            public void error(SAXParseException exception) throws SAXException {
                throw exception;
            }

            @Override
            public void fatalError(SAXParseException exception)
                    throws SAXException {
                throw exception;
            }
        });
        return builder.parse(new ByteArrayInputStream(bytes));
    }

    private static XPathExpression compileBounded(String expression)
            throws Exception {
        XPathFactory factory = XPathFactory.newDefaultInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setProperty("jdk.xml.xpathExprGrpLimit", "8");
        factory.setProperty("jdk.xml.xpathExprOpLimit", "20");
        return factory.newXPath().compile(expression);
    }

    private static int countItems(String xml) throws Exception {
        try (InputStream source = new ByteArrayInputStream(
                xml.getBytes(StandardCharsets.UTF_8))) {
            Document document = parseBounded(source);
            Double count = (Double) compileBounded("count(/items/item)")
                    .evaluate(document, XPathConstants.NUMBER);
            if (count > MAX_MATCHES) {
                throw new IllegalArgumentException("Too many matching items");
            }
            return count.intValue();
        }
    }

    private static void expectParseRejection(String label, String xml)
            throws Exception {
        try {
            countItems(xml);
        } catch (SAXException expected) {
            System.out.println(label + "=rejected");
            return;
        }
        throw new AssertionError(label + " was accepted");
    }

    public static void main(String[] args) throws Exception {
        System.out.println("valid=" + countItems(
                "<items><item/><item/></items>"));

        try {
            countItems("x".repeat(MAX_BYTES + 1));
            throw new AssertionError("oversized input was accepted");
        } catch (IOException expected) {
            System.out.println("byte-limit=rejected");
        }

        expectParseRejection("depth-limit",
                "<n>".repeat(10) + "</n>".repeat(10));
        expectParseRejection("attribute-limit",
                "<items a='1' b='2' c='3' d='4' e='5'"
                        + " f='6' g='7' h='8' i='9'/>");
        expectParseRejection("doctype", "<!DOCTYPE items><items/>");

        try {
            countItems("<items>" + "<item/>".repeat(33) + "</items>");
            throw new AssertionError("oversized result was accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("result-limit=rejected");
        }

        try {
            compileBounded("1 + ".repeat(30) + "1");
            throw new AssertionError("complex expression was accepted");
        } catch (XPathExpressionException expected) {
            System.out.println("xpath-operators=rejected");
        }
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```shell
javac BoundedXmlXPathDemo.java
java BoundedXmlXPathDemo
```

Stdout:

```text
valid=2
byte-limit=rejected
depth-limit=rejected
attribute-limit=rejected
doctype=rejected
result-limit=rejected
xpath-operators=rejected
```

### Điều gì được xác nhận?

1. Một tài liệu nhỏ hợp lệ được chấp nhận và trả đúng hai item.
2. Nguồn dài hơn ngưỡng byte bị từ chối trước khi parser nhận nội dung.
3. Tài liệu nhỏ nhưng sâu hơn mức 8 và phần tử có 9 thuộc tính đều bị parser từ chối.
4. Một DOCTYPE đơn giản không có nguồn ngoài cũng bị từ chối vì chính sách không cho DOCTYPE.
5. Tài liệu có 33 item vẫn nhỏ và parse được, nhưng quy tắc ứng dụng từ chối số item vượt 32.
6. Biểu thức có nhiều toán tử bị chặn ở bước compile theo ngưỡng đã cấu hình.

Các đầu vào thử có kích thước nhỏ, không cần tạo một tài liệu làm cạn bộ nhớ để kiểm chứng. Chương trình không phụ thuộc thông báo lỗi chính xác của parser: nó kiểm tra loại lỗi phù hợp với từng bước và báo nhãn của chính phép thử. Lỗi cấu hình factory/thuộc tính không được coi là một lần từ chối tài liệu đúng chính sách; chúng truyền ra để không che việc cấu hình chưa áp dụng.

`ErrorHandler` ném lại lỗi parse thay vì tiếp tục với một cây chưa hợp lệ. Nó cũng tránh việc mặc định in nội dung lỗi parser ra stderr trong stdout thí nghiệm; trong sản phẩm cần có kênh ghi nhận lỗi có kiểm soát, không có nghĩa mọi lỗi nên bị im lặng.

### Ranh giới của hàm đọc có giới hạn

`parseBounded` đọc tối đa 4097 byte từ nguồn được truyền vào rồi parse một bộ đệm đã giới hạn. Bên gọi sở hữu việc đóng nguồn gốc; `countItems` dùng `try-with-resources`. Ví dụ dùng `ByteArrayInputStream` nên không có mạng hoặc quá trình giải nén, nhưng hàm nhận `InputStream` để chỉ rõ nơi nên đặt ngưỡng trong đường xử lý thật.

Không đưa trước một chuỗi đầu vào khổng lồ vào phiên bản sản phẩm chỉ để tận dụng helper `countItems(String)`: helper đó là tiện ích tạo dữ liệu thử. Với nguồn ngoài, áp `parseBounded` hoặc cơ chế giới hạn tương đương trực tiếp trên nguồn trước khi tạo bản sao không giới hạn.

### Giới hạn kết quả đến sau công việc đếm

`count(/items/item)` trả một số, không tạo danh sách toàn bộ item cho ứng dụng. Tuy nhiên, DOM đã được xây và XPath đã duyệt để tính số đó trước khi `MAX_MATCHES` được kiểm tra. Đây là giới hạn kết quả/nghiệp vụ, không phải bằng chứng heap của parse chỉ đủ cho 32 item.

Ví dụ giữ DOM trong phạm vi cục bộ rồi chỉ trả số đếm. Nếu trả `Node`/`NodeList` ra cache hoặc giữ lâu trong phiên làm việc, các đối tượng kết quả có thể giữ liên hệ với cây; số phần tử in ra ít không có nghĩa toàn bộ DOM đã được giải phóng.

## 7. Giới hạn XPath: kiểm soát cả biểu thức và số lần chạy

Với dịch vụ chỉ cần một số truy vấn cố định, lựa chọn rõ nhất là giữ danh sách truy vấn được phép, nhận tham số dưới dạng dữ liệu và không cho đầu vào tự do sửa cấu trúc biểu thức. Một ngưỡng độ dài chuỗi hoặc số toán tử vẫn không cho biết chính xác thời gian evaluate trên mọi cây.

Các đường chọn rộng, predicate lồng nhau, so sánh nhiều tập nút và gọi lặp cùng truy vấn có thể tiêu thụ CPU theo kích thước dữ liệu. Biểu thức ít toán tử không đồng nghĩa ít công việc. Tương tự, một biểu thức được compile một lần nhưng evaluate hàng nghìn lần vẫn tiêu tài nguyên mỗi lượt.

Trong lớp tiếp nhận truy vấn có thể cấu hình, cần xác định:

- Ai được chọn cấu trúc biểu thức và có thể gọi bao nhiêu lần trên một tài liệu.
- Kích thước/loại DOM mà biểu thức được phép xử lý.
- Có biến, hàm mở rộng hoặc resolver nào dẫn đến I/O hay công việc khác không.
- Có giới hạn bộ nhớ cache biểu thức và số biến thể truy vấn hay không.
- Có cần tách tải truy vấn khỏi các tác vụ phục vụ yêu cầu thông thường không.

`XPathFactory` FSP cũng hạn chế hàm mở rộng theo hợp đồng của nó. Cấu hình phải diễn ra trước `newXPath`; thay feature/property trên factory không tác động ngược lên các XPath đã tạo. [XPathFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/xpath/XPathFactory.html)

Khi dùng DOM đã parse, đặt giới hạn parser ở bước tạo DOM. Nếu thay bằng `evaluate(..., InputSource)`, bộ xử lý có thể tạo parser bên trong; cấu hình một `DocumentBuilderFactory` không được dùng trong đường đó không tự bảo vệ nó. Giữ đường parse tường minh giúp thấy chính xác chính sách nào đã áp dụng.

## 8. Thời hạn chờ không phải thời hạn dừng CPU chắc chắn

JAXP XPath không cung cấp một tham số thời hạn evaluate tổng quát trong các lời gọi thông thường. Đưa evaluate vào executor rồi gọi `future.get(timeout, unit)` chỉ giới hạn thời gian bên gọi **đợi kết quả**. Khi hết thời gian, công việc có thể vẫn đang chạy.

`future.cancel(true)` là nỗ lực hủy, có thể yêu cầu ngắt luồng theo triển khai Future. Không có bảo đảm chung rằng bộ đánh giá XPath sẽ kiểm tra ngắt và dừng ngay trong mọi đường xử lý. Không coi trạng thái Future đã hủy là bằng chứng CPU và bộ nhớ của phép tính đã được thu hồi tại thời điểm đó. [Future: get và cancel](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html)

Với nguồn I/O, đặt thời hạn đọc/kết nối ở tầng nguồn. Với yêu cầu cần mức cách ly mạnh cho công việc không tin cậy, có thể cần worker tiến trình riêng với hạn mức bộ nhớ/CPU và cơ chế kết thúc/thu dọn tiến trình theo chính sách triển khai. Điều đó khác với cố dừng cưỡng bức một luồng đang giữ trạng thái chung trong JVM.

Ngay cả khi có cách ly, vẫn giữ các giới hạn đầu vào và parser để từ chối sớm. Không nên dựa toàn bộ vào một hàng rào cuối sau khi đã tạo lượng công việc vượt ngân sách.

## 9. Mức đồng thời, hàng chờ và bộ nhớ tổng

Giả sử một tài liệu nằm trong ngưỡng hợp lệ và cần một lượng heap đáng kể. Nhiều tài liệu cùng parse/evaluate có thể nhân tổng nhu cầu lên, kèm bộ nhớ hàng chờ, đầu vào và kết quả. Vì vậy giới hạn từng tài liệu phải đi cùng giới hạn đang xử lý và đang chờ.

Pool cố định số worker không tự bảo đảm hàng chờ có dung lượng hữu hạn. Một hàng chờ không giới hạn có thể giữ nhiều byte XML hoặc closure tham chiếu đến đầu vào dù chưa có worker bắt đầu xử lý. Cần chính sách tiếp nhận/từ chối hoặc trì hoãn có kiểm soát, với dung lượng rõ ràng. [ThreadPoolExecutor và chiến lược hàng chờ](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)

Không trả slot đồng thời chỉ vì bên gọi đã timeout nếu công việc nền vẫn chạy và vẫn chiếm tài nguyên. Slot nên gắn với vòng đời thực thi thật, hoặc worker cách ly đã được xác nhận kết thúc. Nếu không, hệ thống có thể liên tục nhận việc mới trong khi công việc cũ chưa dừng.

Đồng thời còn có hợp đồng đối tượng: không để nhiều tác vụ cùng evaluate một `XPath`/`XPathExpression` không an toàn luồng. Tách môi trường hoặc bảo vệ dùng tuần tự phù hợp; giới hạn số tác vụ không tự sửa việc chia sẻ cùng evaluator.

## 10. Khi nào cân nhắc xử lý luồng thay cho DOM + XPath?

Nếu chỉ cần đếm/lọc một số phần tử theo thứ tự, SAX hoặc StAX có thể xử lý dần mà không cần giữ toàn bộ cây. Khi đó có thể đếm số phần tử, tổng văn bản hoặc số bản ghi và dừng khi vượt quy tắc ứng dụng, miễn parser/nguồn cũng có giới hạn phù hợp. [XMLStreamReader](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html)

Đây là thay đổi mô hình xử lý, không chỉ đổi một lời gọi evaluate. Truy vấn cần quay lại tổ tiên, ghép nhiều vùng xa nhau hoặc nhiều lượt truy cập có thể cần thêm trạng thái/bộ đệm. Nếu cuối cùng vẫn gom toàn bộ nội dung vào một danh sách không giới hạn, lợi ích bộ nhớ của đọc dần không còn như dự định.

Giữ cấu hình nguồn ngoài, độ sâu, byte và thời gian ngay cả khi dùng SAX/StAX. “Không dựng DOM” không có nghĩa mọi nguồn XML đều có thể xử lý vô hạn an toàn.

## 11. Chọn ngưỡng và ghi nhận từ chối

Xác định ngưỡng dựa trên tài liệu hợp lệ thực tế: kích thước thường gặp và cực đại cần hỗ trợ, độ sâu do schema/nghiệp vụ quy định, số bản ghi, thời gian đáp ứng và dung lượng môi trường triển khai. Đo cả tổng nhu cầu khi có nhiều yêu cầu, không chỉ một tài liệu mẫu chạy một mình.

Đặt ngưỡng có ý nghĩa theo đơn vị và nơi áp dụng. Ví dụ “XML sau giải nén tối đa X byte, tối đa Y mức phần tử, tối đa Z bản ghi, tối đa K công việc đang chạy và Q đang chờ” rõ hơn “đã bật secure processing”. Sau khi cập nhật JDK hoặc provider, chạy lại các ca ở sát dưới/trên ngưỡng để xác nhận hiệu lực.

Ghi nhận loại giới hạn bị vượt, mốc thời gian, định danh yêu cầu và số liệu kích thước phù hợp. Tránh ghi toàn bộ XML không tin cậy vào log khi từ chối: chính log có thể trở thành nguồn dữ liệu quá lớn hoặc chứa nội dung nhạy cảm. Không tự retry cùng đầu vào bằng cấu hình bỏ giới hạn để “cứu” yêu cầu.

System property có phạm vi toàn JVM và thời điểm đọc không phải một công cụ cấu hình linh động cho từng request. Nếu cần chúng, đặt trước khi JAXP khởi tạo theo hướng dẫn phiên bản; không bật/tắt quanh mỗi evaluate trong hệ thống nhiều luồng. Cấu hình API trên factory của phạm vi xử lý thường dễ truy vết hơn. [Cấu hình và thứ tự ưu tiên java.xml](https://docs.oracle.com/en/java/javase/25/docs/api/java.xml/module-summary.html)

## 12. Các phép kiểm tra cần có

| Nhóm | Ca thử nhỏ có ích |
| --- | --- |
| Đầu vào | Ngay dưới ngưỡng byte, đúng ngưỡng và vượt một byte |
| Cấu trúc | Độ sâu/thuộc tính/tên sát ngưỡng, cây nông nhưng nhiều phần tử |
| Chính sách nguồn | DOCTYPE hoặc tham chiếu nguồn ngoài phải bị từ chối theo hợp đồng |
| XPath | Biểu thức hợp lệ được phép, vượt ngưỡng cấu trúc, dữ liệu tạo nhiều kết quả |
| Vòng đời | Lỗi parse/evaluate vẫn đóng nguồn và trả tài nguyên đã sở hữu |
| Tải tổng | Hàng chờ đầy, nhiều tác vụ hợp lệ đồng thời, bên gọi timeout khi nền còn chạy |
| Cấu hình | JDK/provider không hỗ trợ một thuộc tính bắt buộc phải làm cấu hình thất bại rõ ràng |

Không cần dùng dữ liệu khổng lồ trong các phép thử thường xuyên. Chọn ngưỡng thấp ở fixture rồi tạo dữ liệu nhỏ vượt ngưỡng để kiểm tra đúng lớp từ chối. Các thử nghiệm tải lớn hơn cần môi trường có kiểm soát và mục tiêu đo rõ ràng.

## 13. Tự kiểm tra kiến thức

1. **Cấm DTD đã đủ giới hạn bộ nhớ DOM chưa?** Chưa. Tài liệu không có DTD vẫn có thể rất lớn, sâu hoặc rộng; cần các giới hạn byte/cấu trúc và mức đồng thời.
2. **Đặt entityExpansionLimit bằng 0 có cấm entity không?** Không. Với processing limit đó, giá trị không dương mang nghĩa không giới hạn; dùng cơ chế đúng để từ chối loại cấu trúc không cho phép.
3. **XPath ít toán tử có chắc chạy nhanh không?** Không. Công việc thực tế còn phụ thuộc dữ liệu, cách duyệt và số lần đánh giá.
4. **Future.get hết hạn có chứng minh evaluate đã dừng không?** Không. Đó là hạn chờ kết quả; việc hủy/ngắt không có bảo đảm tổng quát về dừng ngay của bộ XPath.
5. **In tối đa 10 kết quả có ngăn cấp phát mọi kết quả trước đó không?** Không. Cần xem lúc nào kết quả được tạo/giữ và liệu DOM đã được dựng trước đó chưa.
6. **Pool hai worker có chắc chỉ giữ tối đa hai tài liệu không?** Không nếu hàng chờ hoặc tầng tiếp nhận còn giữ nhiều đầu vào. Phải giới hạn cả đang chạy lẫn đang chờ.
